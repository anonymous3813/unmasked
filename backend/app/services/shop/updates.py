"""A sign-in update built from this shopper's purchases, then handed to Photon."""

from backend.app.services.catalog.identity import known_kind
from backend.app.services.shop.cart import contact
from backend.app.services.shop.taste import load_taste


def account_update(user_id: str, name: str = "") -> dict:
    """Describe this shopper's products and what to look at next."""
    orders = _orders(user_id)
    taste = load_taste(user_id)
    return {"text": _text(name, orders, taste), "products": _products(orders, taste)}


def deliver_update(user_id: str, name: str = "", phone: str = "") -> dict:
    """Build the update and text it to the mobile number on this account."""
    payload = account_update(user_id, name)
    from backend.app.integrations.photon_line import send_intro

    text = (
        "Welcome to Unmasked. "
        + payload["text"]
        + " Text this number with a question, a photo, or ask about an order."
    )
    result = send_intro(text, phone) or {}
    payload["sent"] = bool(result.get("sent"))
    payload["reason"] = "" if payload["sent"] else str(result.get("reason") or "Photon did not send the welcome text.")
    return payload


def sms_reply(question: str, phone: str = "", picture: bool = False) -> str:
    """Answer an inbound text from the shopper's orders and recommendations."""
    from backend.app.services.shop.accounts import user_by_phone
    from backend.app.services.shop.agent import answer_question
    from backend.app.services.shop.cart import orders_answer

    user = user_by_phone(phone) or {}
    user_id = str(user.get("id") or "")
    name = str(user.get("name") or "")
    if picture:
        lead = "I received the picture."
    else:
        lead = ""
    asked = " ".join(str(question or "").split())
    if asked.lower() in {"hi", "hello", "hey", "ping", "start"} or (not asked and not picture):
        update = account_update(user_id, name) if user_id else {
            "text": "Welcome to Unmasked. Sign in on the extension with this mobile number so I can see your orders."
        }
        return " ".join(
            part
            for part in (
                lead,
                "Welcome to Unmasked.",
                update["text"],
                "Ask about an order, a product, or send a photo.",
            )
            if part
        )
    remembered = orders_answer(asked, user_id=user_id or "shopper") if user_id and asked else None
    if remembered:
        return " ".join(part for part in (lead, remembered) if part)
    if asked:
        reply = answer_question(asked, title="", page_text=asked, notes=[], visits=[], dossier={})
        if reply:
            return " ".join(part for part in (lead, reply) if part)
    update = account_update(user_id, name) if user_id else {"text": "Sign in on the extension with this mobile number so I can see your orders."}
    if asked and not picture:
        return f"{update['text']} Ask about an order, or name a product and I will look for similar ones."
    return " ".join(part for part in (lead, update["text"]) if part)


def _orders(user_id: str) -> list:
    try:
        return list(contact().past_orders(user_id))
    except KeyError:
        return []


def _text(name: str, orders: list, taste: dict) -> str:
    who = f"{name}, " if name else ""
    if not orders:
        return (
            f"{who}you're signed in. After a checkout or a bill is saved, "
            "the next sign-in covers those products and what to look at next."
        ).strip()
    status = "; ".join(
        f"{order.product_name} is {(order.delivery_status or 'saved').lower()}"
        for order in orders[:4]
    )
    advice = _advice(orders, taste)
    return f"{who}your products: {status}. {advice}".strip()


def _advice(orders: list, taste: dict) -> str:
    brands = list(taste.get("brands") or [])
    avoid = list(taste.get("avoid") or [])
    kinds = []
    for order in orders:
        if _returned(order):
            continue
        kind = known_kind(order.product_name)
        if kind and kind not in kinds:
            kinds.append(kind)
    parts = []
    if brands and kinds:
        parts.append(f"Look at more {kinds[0]}s from {brands[0]}, which you kept.")
    elif kinds:
        parts.append(f"Look at more {kinds[0]}s like the ones you kept.")
    elif brands:
        parts.append(f"Look at more from {brands[0]}, which you kept.")
    if avoid:
        parts.append(f"{avoid[0]} was returned, so those stay off the list.")
    if not parts:
        parts.append("Similar products will follow the brands and colors on these purchases.")
    return " ".join(parts)


def _products(orders: list, taste: dict) -> list[dict]:
    brands = [item.lower() for item in taste.get("brands") or []]
    rows = []
    for order in orders:
        if _returned(order):
            continue
        name = order.product_name
        kind = known_kind(name)
        brand = next((item for item in brands if item in name.lower()), "")
        because = f"More {kind}s" if kind else "More like this"
        if brand:
            because += f" from {brand}"
        rows.append({"name": name, "because": because + ", based on what you kept."})
    return rows[:4]


def _returned(order) -> bool:
    materials = (order.materials or "").lower()
    status = (order.delivery_status or "").lower()
    return "returned:yes" in materials or status == "returned"


