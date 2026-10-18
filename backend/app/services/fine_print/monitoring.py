"""Recheck ordered products and call the shopper when important facts change."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from backend.app.models.agent import (
    ContactPurpose,
    FinePrintOrderContext,
    MessageRole,
    PastOrder,
)
from backend.app.models.fine_print import NotificationKind, ProductNotification, Severity
from backend.app.services.registry.contact import AgentContact

_MAX_POLICIES = 12
_PRICE = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)")
_DELIVERY = re.compile(r"\b(?:deliver|delivery|arrives|ships)\b", re.IGNORECASE)
_SPEC = re.compile(
    r"\b(?:material|size|weight|dimensions|color|capacity)\s*:\s*[^.]+\.?",
    re.IGNORECASE,
)


class OrderMonitor:
    """Watch an order's policies, price, delivery, and specifications.

    Policy links are followed from the product page and then from those
    policy pages. A later check calls the shopper's agent phone when one
    of those facts changes. Questions about the order are answered on the
    same message thread.
    """

    def __init__(self, extractor, contact: AgentContact, policy_depth: int = 2) -> None:
        self.extractor = extractor
        self.contact = contact
        self.policy_depth = policy_depth
        contact.register_answerer(ContactPurpose.FINE_PRINT, self.answer)

    def watch(self, user_id: str, order_id: str, product_name: str, product_url: str) -> FinePrintOrderContext:
        """Store the first snapshot and add the order to the agent profile."""
        context = self._snapshot(product_url)
        self.contact.add_order(
            user_id,
            PastOrder(
                order_id=order_id,
                product_name=product_name,
                product_url=product_url,
                ordered_at=context.checked_at,
                fine_print=context,
            ),
        )
        self.contact.record_message(
            user_id,
            MessageRole.AGENT,
            _baseline_summary(order_id, product_name, context),
            ContactPurpose.FINE_PRINT,
            order_id,
        )
        return context

    def check(self, user_id: str, order_id: str) -> list[ProductNotification]:
        """Recheck the order and call the shopper when facts changed."""
        order = _order(self.contact, user_id, order_id)
        previous = order.fine_print
        current = self._snapshot(str(order.product_url))
        notes = [] if previous is None else _changes(previous, current, str(order.product_url))
        order.fine_print = current
        if notes:
            summary = " ".join(note.message for note in notes)
            self.contact.place_call(user_id, ContactPurpose.FINE_PRINT, summary)
        return notes

    def answer(self, profile, question: str) -> str:
        """Answer a fine-print question from the shopper's stored orders."""
        if not profile.orders:
            return "There are no past orders on this profile."
        text = question.lower()
        if "past order" in text or "my orders" in text:
            listed = ", ".join(
                f"{order.order_id} {order.product_name}"
                + (f" from {order.store}" if order.store else "")
                for order in profile.orders
            )
            return f"Past orders: {listed}."
        order = profile.orders[-1]
        context = order.fine_print
        if context is None:
            return f"Order {order.order_id} has no stored product record yet."
        if any(word in text for word in ("deliver", "arriv", "ship")):
            return context.delivery or "No delivery information is stored for this order."
        if "price" in text or "cost" in text:
            return f"The last checked price is USD {context.price}."
        if "spec" in text or "material" in text:
            return "Specifications: " + "; ".join(context.specifications)
        if any(word in text for word in ("policy", "return", "damage", "warranty")):
            return "\n".join(context.policies.values()) or "No policy text is stored for this order."
        return (
            f"{order.product_name}, order {order.order_id}: "
            f"price USD {context.price}. {context.delivery or ''}"
        ).strip()

    def _snapshot(self, product_url: str) -> FinePrintOrderContext:
        page_text, policies = self._policies(product_url)
        return FinePrintOrderContext(
            price=_price(page_text),
            delivery=_sentence(_delivery_sentence, page_text),
            specifications=_specifications(page_text),
            policies=policies,
            checked_at=datetime.now(timezone.utc),
        )

    def _policies(self, product_url: str) -> tuple[str, dict[str, str]]:
        root = self.extractor.extract(product_url)
        policies: dict[str, str] = {}
        seen = {_url_key(product_url)}
        frontier = [(document, 1) for document in root.documents]
        while frontier and len(policies) < _MAX_POLICIES:
            document, depth = frontier.pop(0)
            key = _url_key(str(document.url))
            if key in seen:
                continue
            seen.add(key)
            policies[key] = document.extracted_text
            if depth >= self.policy_depth:
                continue
            nested = self.extractor.extract(key)
            for child in nested.documents:
                frontier.append((child, depth + 1))
        return root.page_text, policies


def _order(contact: AgentContact, user_id: str, order_id: str) -> PastOrder:
    for order in contact.profile(user_id).orders:
        if order.order_id == order_id:
            return order
    raise KeyError(f"Unknown order: {order_id}")


def _changes(
    previous: FinePrintOrderContext,
    current: FinePrintOrderContext,
    product_url: str,
) -> list[ProductNotification]:
    notes: list[ProductNotification] = []
    created_at = current.checked_at
    if previous.price != current.price and current.price:
        notes.append(
            _note(
                NotificationKind.PRICE,
                "Price changed",
                f"The price changed from USD {previous.price} to USD {current.price}.",
                product_url,
                Severity.HIGH,
                created_at,
            )
        )
    if previous.delivery != current.delivery and current.delivery:
        notes.append(
            _note(
                NotificationKind.PRODUCT_INFO,
                "Delivery update",
                f"Delivery changed from {previous.delivery} to {current.delivery}",
                product_url,
                Severity.MEDIUM,
                created_at,
            )
        )
    if previous.specifications != current.specifications:
        notes.append(
            _note(
                NotificationKind.PRODUCT_INFO,
                "Specification change",
                "Specifications changed from "
                f"{'; '.join(previous.specifications)} to {'; '.join(current.specifications)}.",
                product_url,
                Severity.LOW,
                created_at,
            )
        )
    changed = [
        (url, text)
        for url, text in current.policies.items()
        if previous.policies.get(url) != text
    ]
    if changed:
        details = " ".join(f"{url}: {text}" for url, text in changed)
        notes.append(
            _note(
                NotificationKind.CONCERN,
                "Policy update",
                f"A product policy changed. {details}",
                changed[0][0],
                Severity.HIGH,
                created_at,
            )
        )
    return notes


def _note(kind, title, message, source_url, severity, created_at) -> ProductNotification:
    return ProductNotification(
        kind=kind,
        title=title,
        message=message,
        source_url=source_url,
        created_at=created_at,
        severity=severity,
    )


def _baseline_summary(order_id: str, product_name: str, context: FinePrintOrderContext) -> str:
    delivery = context.delivery or "Delivery is not listed."
    price = f"USD {context.price}" if context.price else "Price is not listed."
    return f"Order {order_id} for {product_name} is being watched. Price {price}. {delivery}"


def _price(text: str) -> str | None:
    match = _PRICE.search(text)
    if match is None:
        return None
    return f"{Decimal(match.group(1).replace(',', '')):.2f}"


def _delivery_sentence(sentence: str) -> bool:
    return _DELIVERY.search(sentence) is not None


def _sentence(predicate, text: str) -> str | None:
    pieces = re.split(r"(?<=[.!?])\s+", text.strip())
    for piece in pieces:
        cleaned = " ".join(piece.split())
        if predicate(cleaned):
            return cleaned
    return None


def _specifications(text: str) -> list[str]:
    return [" ".join(match.group(0).split()) for match in _SPEC.finditer(text)]


def _url_key(url: str) -> str:
    return str(url).rstrip("/")
