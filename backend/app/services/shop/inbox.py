"""Messages and calls on the shopper's assistant profile."""

import re

from backend.app.models.agent import ContactPurpose, MessageRole
from backend.app.services.shop.agent import answer_question
from backend.app.services.shop.cart import contact, orders_answer

_CART = re.compile(r"\bcart\b", re.IGNORECASE)


def inbox(shopper=None, user_id: str = "shopper") -> dict:
    """Return this shopper's messages, calls, and orders."""
    shopper = shopper or contact()
    try:
        profile = shopper.profile(user_id)
    except KeyError:
        return {"messages": [], "calls": [], "orders": []}
    return {
        "messages": [
            {"role": message.role.value, "body": message.body}
            for message in profile.messages
        ],
        "calls": [{"summary": call.summary} for call in profile.calls],
        "orders": [
            {
                "orderId": order.order_id,
                "name": order.product_name,
                "store": order.store,
                "price": order.price,
            }
            for order in profile.orders
        ],
    }


def send_message(
    text: str,
    cart: list | None = None,
    shopper=None,
    complete=None,
    notes: list | None = None,
    user_id: str = "shopper",
) -> dict:
    """Save a message and answer it from the cart, orders, and page annotations."""
    shopper = shopper or contact()
    _ready(shopper, user_id)
    shopper.record_message(user_id, MessageRole.USER, text.strip(), ContactPurpose.FINE_PRINT)
    answer = _reply(text, cart or [], shopper, complete, notes or [], user_id)
    shopper.record_message(user_id, MessageRole.AGENT, answer, ContactPurpose.FINE_PRINT)
    return {"answer": answer, "inbox": inbox(shopper, user_id)}


def place_call(cart: list | None = None, shopper=None, notes: list | None = None, user_id: str = "shopper") -> dict:
    """Call the assistant about the cart, orders, and page annotations."""
    shopper = shopper or contact()
    _ready(shopper, user_id)
    summary = _brief(cart or [], shopper, notes or [], user_id)
    call = shopper.place_call(user_id, ContactPurpose.FINE_PRINT, summary)
    return {"summary": call.summary, "inbox": inbox(shopper, user_id)}


def _ready(shopper, user_id: str) -> None:
    try:
        shopper.profile(user_id)
    except KeyError:
        shopper.open_profile(user_id, "+1 415 555 0199")


def _reply(text: str, cart: list, shopper, complete, notes: list, user_id: str) -> str:
    if _CART.search(text or ""):
        return _cart_line(cart)
    remembered = orders_answer(text, shopper, user_id)
    if remembered is not None:
        return remembered
    orders = _order_line(shopper, user_id)
    context = f"Cart: {_cart_line(cart)}\nOrders: {orders}\nAnnotations: {_notes_line(notes)}"
    try:
        return answer_question(
            text,
            title="Shopper inbox",
            page_text=context,
            notes=notes,
            complete=complete,
        )
    except TypeError:
        return answer_question(
            text,
            title="Shopper inbox",
            page_text=context,
        )


def _brief(cart: list, shopper, notes: list, user_id: str) -> str:
    summary = f"{_cart_line(cart)} {orders_answer('what are my orders', shopper, user_id)}"
    annotations = _notes_line(notes)
    if not annotations:
        return summary
    return f"{summary} On this page: {annotations}"


def _notes_line(notes: list) -> str:
    parts = []
    for note in notes:
        message = str(note.get("message") or note.get("label") or "").strip()
        if not message:
            continue
        title = str(note.get("title") or "Note")
        parts.append(f"{title}: {message}")
    return " ".join(parts[:6])


def _cart_line(cart: list) -> str:
    if not cart:
        return "Your cart is empty."
    items = "; ".join(
        f"{item.get('name')} from {item.get('store')} (${item.get('price')})"
        for item in cart
        if item.get("name")
    )
    return f"In your cart: {items}."


def _order_line(shopper, user_id: str) -> str:
    return orders_answer("what are my orders", shopper, user_id) or "No orders yet."
