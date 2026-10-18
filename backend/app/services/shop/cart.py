"""The assistant's phone, cross-store cart, and the orders it remembers."""

import os
import re
from datetime import datetime, timedelta, timezone

from backend.app.models.agent import ContactPurpose, FinePrintOrderContext, MessageRole, PastOrder
from backend.app.services.registry.contact import AgentContact

ASSISTANT_NAME = "Your Online Assistant"
ASSISTANT_PHONE = "+1 415 555 0199"
SHOPPER_ID = "shopper"
_ORDER_QUESTION = re.compile(
    r"\b(?:my orders?|past orders?|what did i (?:buy|order)|orders? from|track my|"
    r"where(?:'s| is) my|order status|shipping|delivery|purchases?|arriv(?:e|al|es)|when (?:does|will|is))\b",
    re.IGNORECASE,
)
_STAGES = (
    (0, "Placed", "Recorded with the assistant."),
    (2, "Shipped", "The store has the order."),
    (5, "Out for delivery", "On the way to you."),
    (8, "Delivered", "The assistant marks this delivered."),
)
_PLACEHOLDER_DAYS = (3, 5, 7)

_contact: AgentContact | None = None


def assistant() -> dict:
    """Return the name and the project's iMessage number."""
    from backend.app.integrations.photon_line import agent_line

    line = agent_line()
    phone = str(line.get("phone") or "")
    if phone:
        contact().open_profile(SHOPPER_ID, phone)
    return {
        "name": ASSISTANT_NAME,
        "phone": phone,
        "phoneDisplay": _display_phone(phone) if phone else "",
        "lineStatus": line.get("status") or "",
    }


def _display_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def contact() -> AgentContact:
    """Return the one profile this shop server remembers."""
    global _contact
    if _contact is None:
        _contact = AgentContact()
        _contact.open_profile(SHOPPER_ID, ASSISTANT_PHONE)
    return _contact


def _order_label(user_id: str, number: int) -> str:
    """Keep the shared shopper's A0001 ids, and give each account its own."""
    label = f"A{number:04d}"
    if user_id == SHOPPER_ID:
        return label
    tag = re.sub(r"[^a-zA-Z0-9]", "", user_id)[:8] or "user"
    return f"{tag}-{label}"


def purchase(items: list[dict], shopper: AgentContact | None = None, user_id: str = SHOPPER_ID) -> dict:
    """Record one order per store listing and return what the assistant remembers."""
    shopper = shopper or contact()
    try:
        shopper.profile(user_id)
    except KeyError:
        shopper.open_profile(user_id, ASSISTANT_PHONE)
    saved = []
    now = datetime.now(timezone.utc)
    existing = shopper.past_orders(user_id)
    for offset, item in enumerate(items, start=1):
        order_id = _order_label(user_id, len(existing) + offset)
        score = item.get("environmentScore")
        if score is None:
            score = item.get("environment_score")
        from backend.app.services.shop.taste import describe

        facts = describe(str(item["name"]), str(item.get("materials") or ""))
        brand = str(item.get("brand") or facts["brand"])
        color = str(item.get("color") or facts["color"])
        returned = bool(item.get("returned")) or facts["returned"]
        materials = " ".join(
            part
            for part in (
                str(item.get("materials") or item.get("message") or item.get("quotation") or ""),
                f"brand:{brand}" if brand else "",
                f"color:{color}" if color else "",
                "returned:yes" if returned else "",
            )
            if part
        )
        delivery_date = _parse_date(item.get("deliveryDate") or item.get("delivery_date"))
        if delivery_date is None:
            delivery_date = _placeholder_date(now, len(existing) + offset - 1)
        order = PastOrder(
            order_id=order_id,
            product_name=str(item["name"]),
            product_url=str(item["url"]),
            ordered_at=now,
            store=str(item.get("store") or ""),
            price=str(item.get("price") or ""),
            environment_score=int(score) if score is not None and str(score).strip() != "" else None,
            materials=materials,
            delivery_date=delivery_date,
            fine_print=FinePrintOrderContext(price=str(item.get("price") or ""), checked_at=now),
        )
        shopper.add_order(user_id, order)
        saved.append(order)
        from backend.app.integrations.supabase_store import save_order

        save_order(order, user_id)
    summary = _summary(shopper.past_orders(user_id))
    shopper.record_message(user_id, MessageRole.AGENT, summary, ContactPurpose.FINE_PRINT)
    if shopper is contact():
        refresh_delivery(now, shopper, user_id=user_id)
    return {"answer": summary, "orders": [_public(order) for order in saved]}


def mark_returned(order_id: str, shopper: AgentContact | None = None, user_id: str = SHOPPER_ID) -> dict:
    """Remember that the shopper sent this order back."""
    shopper = shopper or contact()
    try:
        orders = shopper.past_orders(user_id)
    except KeyError:
        orders = []
    for order in orders:
        if order.order_id != order_id:
            continue
        if "returned:yes" not in order.materials:
            order.materials = f"{order.materials} returned:yes".strip()
        order.delivery_status = "Returned"
        from backend.app.integrations.supabase_store import save_order

        save_order(order, user_id)
        return {"orderId": order_id, "status": "Returned"}
    return {"orderId": order_id, "status": "missing"}


def orders_answer(question: str, shopper: AgentContact | None = None, user_id: str = SHOPPER_ID) -> str | None:
    """Answer an order question from the profile, or leave other questions alone."""
    if _ORDER_QUESTION.search(question or "") is None:
        return None
    shopper = shopper or contact()
    try:
        orders = shopper.past_orders(user_id)
    except KeyError:
        orders = []
    if not orders:
        return "You don't have any orders on this assistant yet."
    return _summary(orders)


def set_delivery_date(
    order_id: str,
    delivery_date: datetime | str,
    shopper: AgentContact | None = None,
    send=None,
    user_id: str = SHOPPER_ID,
) -> dict:
    """Update one order's arrival date, persist it, and text when the date changes."""
    shopper = shopper or contact()
    stamp = _parse_date(delivery_date)
    if stamp is None:
        return {"orderId": order_id, "status": "invalid_date"}
    try:
        orders = shopper.past_orders(user_id)
    except KeyError:
        orders = []
    for order in orders:
        if order.order_id != order_id:
            continue
        order.delivery_date = stamp
        from backend.app.integrations.supabase_store import save_order

        save_order(order, user_id)
        refresh_delivery(shopper=shopper, send=send, user_id=user_id)
        return {"orderId": order_id, **_public(order)}
    return {"orderId": order_id, "status": "missing"}


def ensure_delivery_dates(shopper: AgentContact | None = None, user_id: str = SHOPPER_ID) -> list[PastOrder]:
    """Fill placeholder delivery dates on orders that do not have one yet."""
    shopper = shopper or contact()
    try:
        orders = shopper.past_orders(user_id)
    except KeyError:
        return []
    from backend.app.integrations.supabase_store import save_order

    for index, order in enumerate(orders):
        if order.delivery_date is not None:
            continue
        if "returned:yes" in (order.materials or "") or order.delivery_status == "Returned":
            continue
        order.delivery_date = _placeholder_date(order.ordered_at, index)
        save_order(order, user_id)
    return orders


def _summary(orders: list[PastOrder]) -> str:
    lines = ["Your orders", ""]
    for index, order in enumerate(orders, start=1):
        store = order.store or "Store"
        price = f"${order.price}" if order.price else "price n/a"
        arrives = _pretty_date(order.delivery_date) if order.delivery_date else "date n/a"
        status = order.delivery_status or "saved"
        lines.append(f"{index}. {order.product_name}")
        lines.append(f"   {store} · {price}")
        lines.append(f"   Status: {status}")
        lines.append(f"   Arrives: {arrives}")
        lines.append("")
    return "\n".join(lines).rstrip()


def refresh_delivery(now: datetime | None = None, shopper: AgentContact | None = None, send=None, user_id: str = SHOPPER_ID) -> dict:
    """Advance delivery status, keep placeholder dates, and text when status or date changes."""
    now = now or datetime.now(timezone.utc)
    shopper = shopper or contact()
    ensure_delivery_dates(shopper, user_id)
    if send is None:
        send = lambda text: _notify(text, user_id)
    from backend.app.services.registry.log import record

    try:
        saved = shopper.past_orders(user_id)
    except KeyError:
        saved = []
    orders = []
    for order in saved:
        if "returned:yes" in (order.materials or ""):
            status, note = "Returned", "You marked this order returned."
        else:
            status, note = _stage(order.ordered_at, now)
        order.delivery_status = status
        date_key = _date_key(order.delivery_date)
        changed_status = order.notified_status != status
        changed_date = bool(date_key) and order.notified_delivery_date != date_key
        if changed_status or changed_date:
            text = _delivery_text(
                order,
                status,
                note,
                changed_date=changed_date,
                previous_date=order.notified_delivery_date,
            )
            result = send(text) or {}
            order.notified_status = status
            if date_key:
                order.notified_delivery_date = date_key
            detail = "Delivery text sent." if result.get("sent") else str(result.get("reason") or "Delivery text was not sent.")
            record("intro", f"{order.product_name} · {status}", detail, str(order.product_url))
            from backend.app.integrations.supabase_store import save_order

            save_order(order, user_id)
        orders.append(
            {
                **_public(order),
                "status": status,
                "statusNote": note,
                "environmentScore": order.environment_score,
                "materials": order.materials,
            }
        )
    scores = [item["environmentScore"] for item in orders if isinstance(item["environmentScore"], int)]
    footprint = round(sum(scores) / len(scores)) if scores else None
    return {"orders": orders, "footprint": footprint}


def _notify(text: str, user_id: str) -> dict:
    """Text the account phone, or the open iMessage space when one is configured."""
    from backend.app.integrations.photon_line import send_intro, send_to_space
    from backend.app.services.shop.accounts import user_by_id

    user = user_by_id(user_id) or {}
    phone = str(user.get("phone") or "")
    space = os.environ.get("PHOTON_SPACE_ID", "")
    agent = os.environ.get("PHOTON_IMESSAGE_USER_ID") or ""
    if space.startswith("pho_spc_"):
        sent = send_to_space(space, text, agent)
        if sent.get("sent"):
            return sent
    return send_intro(text, phone)


def _delivery_text(order: PastOrder, status: str, note: str, changed_date: bool, previous_date: str) -> str:
    arrives = _pretty_date(order.delivery_date)
    if changed_date and previous_date:
        return "\n".join(
            [
                "Delivery update",
                "",
                order.product_name,
                f"Now arrives: {arrives}",
                f"Was: {_pretty_date(previous_date)}",
                f"Status: {status}",
            ]
        )
    lines = ["Delivery update", "", order.product_name, f"Status: {status}"]
    if arrives:
        lines.append(f"Arrives: {arrives}")
    if note:
        lines.append(note)
    return "\n".join(lines)


def _placeholder_date(ordered_at: datetime, index: int) -> datetime:
    stamp = ordered_at if ordered_at.tzinfo else ordered_at.replace(tzinfo=timezone.utc)
    days = _PLACEHOLDER_DAYS[index % len(_PLACEHOLDER_DAYS)]
    return (stamp + timedelta(days=days)).replace(hour=17, minute=0, second=0, microsecond=0)


def _parse_date(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _date_key(value: datetime | str | None) -> str:
    stamp = _parse_date(value)
    if stamp is None:
        return ""
    return stamp.date().isoformat()


def _pretty_date(value: datetime | str | None) -> str:
    stamp = _parse_date(value)
    if stamp is None:
        return str(value or "")
    return stamp.strftime("%a %b %d")


def _stage(ordered_at: datetime, now: datetime) -> tuple[str, str]:
    minutes = max(0, (now - ordered_at).total_seconds() / 60)
    status, note = _STAGES[0][1], _STAGES[0][2]
    for mark, name, detail in _STAGES:
        if minutes >= mark:
            status, note = name, detail
    return status, note


def _public(order: PastOrder) -> dict:
    return {
        "orderId": order.order_id,
        "name": order.product_name,
        "store": order.store,
        "price": order.price,
        "url": str(order.product_url),
        "environmentScore": order.environment_score,
        "materials": order.materials,
        "status": order.delivery_status,
        "deliveryDate": order.delivery_date.isoformat() if order.delivery_date else "",
    }
