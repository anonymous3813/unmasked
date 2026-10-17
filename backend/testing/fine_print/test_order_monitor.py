"""Post-order checks and the shared agent phone and message profile."""

from datetime import datetime, timezone

from backend.app.models.agent import ContactPurpose
from backend.app.models.fine_print import FinePrintExtraction, PolicyDocument
from backend.app.services.agent_contact import AgentContact
from backend.app.services.fine_print.monitoring import OrderMonitor

NOW = datetime(2026, 10, 17, 16, 30, tzinfo=timezone.utc)
PRODUCT = "https://shop.example/products/jacket"
SHIPPING = "https://shop.example/help/shipping"
DAMAGE = "https://shop.example/help/damage"


class ScriptedExtractor:
    def __init__(self, pages: dict[str, FinePrintExtraction]) -> None:
        self.pages = pages

    def extract(self, url: str) -> FinePrintExtraction:
        return self.pages[url.rstrip("/")]


def _page(url: str, text: str, documents: list[PolicyDocument]) -> FinePrintExtraction:
    return FinePrintExtraction(
        source_url=url,
        page_text=text,
        documents=documents,
        retrieved_at=NOW,
    )


def _document(url: str, text: str) -> PolicyDocument:
    return PolicyDocument(url=url, extracted_text=text, retrieved_at=NOW)


def _pages(price: str, delivery: str, material: str, damage: str) -> dict[str, FinePrintExtraction]:
    damage_doc = _document(DAMAGE, damage)
    shipping_doc = _document(SHIPPING, "Standard shipping terms apply.")
    return {
        PRODUCT: _page(
            PRODUCT,
            f"Alpine Jacket. Price {price}. {delivery} Material: {material}.",
            [shipping_doc],
        ),
        SHIPPING: _page(SHIPPING, "Standard shipping terms apply.", [damage_doc]),
    }


def test_monitor_follows_nested_policies_and_calls_when_the_order_changes():
    contact = AgentContact()
    contact.open_profile("shopper-1", "+15551212000")
    monitor = OrderMonitor(ScriptedExtractor(_pages("$120", "Arrives in 5 days.", "100% polyester", "Report damage within 48 hours.")), contact)

    first = monitor.watch("shopper-1", "1001", "Alpine Jacket", PRODUCT)

    assert SHIPPING in first.policies
    assert DAMAGE in first.policies
    assert first.price == "120.00"
    assert first.delivery == "Arrives in 5 days."
    assert first.specifications == ["Material: 100% polyester."]
    assert contact.calls("shopper-1") == []
    assert [order.order_id for order in contact.past_orders("shopper-1")] == ["1001"]

    monitor.extractor = ScriptedExtractor(
        _pages("$140", "Arrives in 12 days.", "80% polyester", "Report damage within 24 hours.")
    )
    notes = monitor.check("shopper-1", "1001")

    titles = [note.title for note in notes]
    assert titles == ["Price changed", "Delivery update", "Specification change", "Policy update"]
    call = contact.calls("shopper-1")[0]
    assert call.phone_number == "+15551212000"
    assert call.purpose is ContactPurpose.FINE_PRINT
    assert "140.00" in call.summary
    assert "12 days" in call.summary

    delivery_reply = contact.ask("shopper-1", "What is the delivery for my order?")
    orders_reply = contact.ask("shopper-1", "Show my past orders")
    claim_reply = contact.ask(
        "shopper-1",
        "Was the waterproof claim true?",
        purpose=ContactPurpose.CLAIM_VALIDATION,
    )

    assert "12 days" in delivery_reply.body
    assert "1001" in orders_reply.body
    assert "Alpine Jacket" in orders_reply.body
    assert claim_reply.purpose is ContactPurpose.CLAIM_VALIDATION
    assert "12 days" not in claim_reply.body
    assert "polyester" not in claim_reply.body
    assert [message.purpose for message in contact.profile("shopper-1").messages][-1] is ContactPurpose.CLAIM_VALIDATION
    assert contact.profile("shopper-1").phone_number == "+15551212000"
