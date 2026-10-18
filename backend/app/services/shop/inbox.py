"""Messages and calls on the shopper's assistant profile."""

import re

from backend.app.models.agent import ContactPurpose, MessageRole
from backend.app.services.shop.agent import answer_question
from backend.app.services.shop.cart import contact, orders_answer

_CART = re.compile(r"\bcart\b", re.IGNORECASE)


def inbox(shopper=None) -> dict:
    """Return the assistant's messages, calls, and orders."""
    profile = (shopper or contact()).profile("shopper")
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
) -> dict:
    """Save a message and answer it from the cart, orders, and page annotations."""
    shopper = shopper or contact()
    _ready(shopper)
    shopper.record_message("shopper", MessageRole.USER, text.strip(), ContactPurpose.FINE_PRINT)
    answer = _reply(text, cart or [], shopper, complete, notes or [])
    shopper.record_message("shopper", MessageRole.AGENT, answer, ContactPurpose.FINE_PRINT)
    return {"answer": answer, "inbox": inbox(shopper)}


def place_call(cart: list | None = None, shopper=None, notes: list | None = None) -> dict:
    """Call the assistant about the cart, orders, and page annotations."""
    shopper = shopper or contact()
    _ready(shopper)
    summary = _brief(cart or [], shopper, notes or [])
    call = shopper.place_call("shopper", ContactPurpose.FINE_PRINT, summary)
    return {"summary": call.summary, "inbox": inbox(shopper)}


def _ready(shopper) -> None:
    try:
        shopper.profile("shopper")
    except KeyError:
        shopper.open_profile("shopper", "+1 415 555 0199")


def _reply(text: str, cart: list, shopper, complete, notes: list) -> str:
    if _CART.search(text or ""):
        return _cart_line(cart)
    remembered = orders_answer(text, shopper)
    if remembered is not None:
        return remembered
    orders = _order_line(shopper)
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


def _brief(cart: list, shopper, notes: list) -> str:
    summary = f"{_cart_line(cart)} {orders_answer('what are my orders', shopper)}"
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


def _order_line(shopper) -> str:
    return orders_answer("what are my orders", shopper) or "No orders yet."
