"""Shopper notifications for hidden concerns, price, and product availability."""

from datetime import datetime, timezone

from backend.app.models.fine_print import (
    FinePrintAnalysisResult,
    NotificationKind,
    PolicyDocument,
    PriceWithTax,
    RiskCategory,
    RiskFinding,
    Severity,
)
from backend.app.services.fine_print.notifications import FinePrintNotifier

NOW = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc)
PAGE_URL = "https://shop.example/products/jacket"
RETURNS_URL = "https://shop.example/help/returns"
DAMAGE_URL = "https://shop.example/help/damage"


def _result() -> FinePrintAnalysisResult:
    return FinePrintAnalysisResult(
        document=PolicyDocument(
            url=PAGE_URL,
            extracted_text="Alpine Jacket. Price $120. In stock. Free 365-day returns.",
            retrieved_at=NOW,
        ),
        findings=[
            RiskFinding(
                category=RiskCategory.DAMAGE_POLICY,
                severity=Severity.MEDIUM,
                explanation="Unreported shipping damage becomes the shopper's bill.",
                evidence_quotation="Report shipping damage within 48 hours.",
                source_url=DAMAGE_URL,
            ),
            RiskFinding(
                category=RiskCategory.RESTOCKING_FEE,
                severity=Severity.HIGH,
                explanation="Opening the jacket adds a fee.",
                evidence_quotation="Opened items incur a 15% restocking fee.",
                source_url=RETURNS_URL,
            ),
        ],
        analyzed_at=NOW,
        price=PriceWithTax(
            listed_price="120.00",
            currency="USD",
            tax_included=False,
            price_with_tax="130.20",
            tax_rate="8.5%",
            explanation=(
                "The page shows USD 120.00. Sales tax of 8.5% is not included. "
                "With tax, the price is USD 130.20."
            ),
            evidence_quotation="Sales tax of 8.5% is added at checkout.",
            source_url=RETURNS_URL,
        ),
    )


def test_notifier_reports_price_concerns_and_availability():
    notes = FinePrintNotifier().build(_result())

    assert [note.kind for note in notes] == [
        NotificationKind.PRICE,
        NotificationKind.CONCERN,
        NotificationKind.CONCERN,
        NotificationKind.PRODUCT_INFO,
    ]
    assert notes[0].title == "Price with tax"
    assert "USD 130.20" in notes[0].message
    assert notes[1].title == "Restocking fee"
    assert notes[1].severity is Severity.HIGH
    assert "15% restocking fee" in notes[1].message
    assert str(notes[1].source_url).rstrip("/") == RETURNS_URL
    assert notes[2].title == "Damage policy"
    assert notes[3].title == "Availability"
    assert "In stock" in notes[3].message
    assert all(note.created_at == NOW for note in notes)


def test_notifier_is_empty_when_the_page_has_nothing_new_to_say():
    result = _result().model_copy(
        update={
            "findings": [],
            "price": None,
            "document": PolicyDocument(
                url=PAGE_URL,
                extracted_text="Alpine Jacket. Price $120.",
                retrieved_at=NOW,
            ),
        }
    )

    assert FinePrintNotifier().build(result) == []
