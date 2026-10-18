"""The assistant's phone, cross-store cart, and the orders it remembers."""

import re
from datetime import datetime, timezone

from backend.app.models.agent import ContactPurpose, FinePrintOrderContext, MessageRole, PastOrder
from backend.app.services.registry.contact import AgentContact

ASSISTANT_NAME = "Your Online Assistant"
ASSISTANT_PHONE = "+1 415 555 0199"
SHOPPER_ID = "shopper"
_ORDER_QUESTION = re.compile(
    r"\b(?:my orders|past orders|what did i (?:buy|order)|orders from|track my)\b",
    re.IGNORECASE,
)
_STAGES = (
    (0, "Placed", "Recorded with the assistant."),
    (2, "Shipped", "The store has the order."),
    (5, "Out for delivery", "On the way to you."),
    (8, "Delivered", "The assistant marks this delivered."),
)

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


def purchase(items: list[dict], shopper: AgentContact | None = None) -> dict:
    """Record one order per store listing and return what the assistant remembers."""
    shopper = shopper or contact()
    if shopper is not contact():
        try:
            shopper.profile(SHOPPER_ID)
        except KeyError:
            shopper.open_profile(SHOPPER_ID, ASSISTANT_PHONE)
    saved = []
    now = datetime.now(timezone.utc)
    existing = shopper.past_orders(SHOPPER_ID)
    for offset, item in enumerate(items, start=1):
        order_id = f"A{len(existing) + offset:04d}"
        score = item.get("environmentScore")
        if score is None:
            score = item.get("environment_score")
        order = PastOrder(
            order_id=order_id,
            product_name=str(item["name"]),
            product_url=str(item["url"]),
            ordered_at=now,
            store=str(item.get("store") or ""),
            price=str(item.get("price") or ""),
            environment_score=int(score) if score is not None and str(score).strip() != "" else None,
            materials=str(item.get("materials") or item.get("message") or item.get("quotation") or ""),
            fine_print=FinePrintOrderContext(price=str(item.get("price") or ""), checked_at=now),
        )
        shopper.add_order(SHOPPER_ID, order)
        saved.append(order)
        from backend.app.integrations.supabase_store import save_order

        save_order(order)
    summary = _summary(shopper.past_orders(SHOPPER_ID))
    shopper.record_message(SHOPPER_ID, MessageRole.AGENT, summary, ContactPurpose.FINE_PRINT)
    if shopper is contact():
        refresh_delivery(now, shopper)
    return {"answer": summary, "orders": [_public(order) for order in saved]}


def orders_answer(question: str, shopper: AgentContact | None = None) -> str | None:
    """Answer an order question from the profile, or leave other questions alone."""
    if _ORDER_QUESTION.search(question or "") is None:
        return None
    shopper = shopper or contact()
    try:
        orders = shopper.past_orders(SHOPPER_ID)
    except KeyError:
        orders = []
    if not orders:
        return "You don't have any orders on this assistant yet."
    return _summary(orders)


def _summary(orders: list[PastOrder]) -> str:
    grouped: dict[str, list[str]] = {}
    for order in orders:
        store = order.store or "Store"
        price = f" (${order.price})" if order.price else ""
        grouped.setdefault(store, []).append(f"{order.order_id} {order.product_name}{price}")
    parts = [f"{store}: {'; '.join(lines)}" for store, lines in grouped.items()]
    return "Your orders are on this assistant. " + " ".join(parts)


def refresh_delivery(now: datetime | None = None, shopper: AgentContact | None = None, send=None) -> dict:
    """Advance each order's delivery status and text the shopper when it changes."""
    now = now or datetime.now(timezone.utc)
    shopper = shopper or contact()
    if send is None:
        from backend.app.integrations.photon_line import send_intro

        send = send_intro
    from backend.app.services.registry.log import record

    try:
        saved = shopper.past_orders(SHOPPER_ID)
    except KeyError:
        saved = []
    orders = []
    for order in saved:
        status, note = _stage(order.ordered_at, now)
        order.delivery_status = status
        if order.notified_status != status:
            score = f"{order.environment_score} out of 100" if order.environment_score is not None else "not scored"
            text = f"{order.product_name} is {status.lower()}. {note} Environment score {score}."
            result = send(text) or {}
            order.notified_status = status
            detail = "Delivery text sent." if result.get("sent") else str(result.get("reason") or "Delivery text was not sent.")
            record("intro", f"{order.product_name} · {status}", detail, str(order.product_url))
            from backend.app.integrations.supabase_store import save_order

            save_order(order)
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
    }
