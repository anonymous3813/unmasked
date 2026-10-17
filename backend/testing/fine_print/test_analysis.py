"""Semantic analysis of fine print that is not already visible on the page."""

import os
from datetime import datetime, timezone

from backend.app.models.fine_print import FinePrintExtraction, PolicyDocument
from backend.app.services.fine_print.analysis import FinePrintAnalyzer, _load_env_file

RETRIEVED_AT = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
PAGE_URL = "https://shop.example/products/jacket"
RETURNS_URL = "https://shop.example/help/returns"
DAMAGE_URL = "https://shop.example/help/damage"

PAGE_TEXT = "Alpine Jacket. Price $120. Free 365-day returns on unopened items."
RESTOCKING = "Opened items incur a 15% restocking fee."
DAMAGE = "Report shipping damage within 48 hours or the customer is responsible for repair costs."
TAX = "Sales tax of 8.5% is added at checkout."
VISIBLE_RETURN = "Free 365-day returns on unopened items."


def _extraction() -> FinePrintExtraction:
    return FinePrintExtraction(
        source_url=PAGE_URL,
        page_text=PAGE_TEXT,
        documents=[
            PolicyDocument(
                url=RETURNS_URL,
                extracted_text=f"{RESTOCKING} {TAX}",
                retrieved_at=RETRIEVED_AT,
            ),
            PolicyDocument(
                url=DAMAGE_URL,
                extracted_text=DAMAGE,
                retrieved_at=RETRIEVED_AT,
            ),
        ],
        retrieved_at=RETRIEVED_AT,
    )


def _analyze_document(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    if "Price $120" in text:
        fields["ListedPrice"] = "$120"
    if VISIBLE_RETURN in text:
        fields["ReturnRestriction"] = VISIBLE_RETURN
    if RESTOCKING in text:
        fields["RestockingFee"] = RESTOCKING
    if "8.5%" in text:
        fields["SalesTaxRate"] = "8.5%"
    if DAMAGE in text:
        fields["DamagePolicy"] = DAMAGE
    return fields


def test_analyze_hides_concerns_already_on_the_page():
    result = FinePrintAnalyzer(analyze_document=_analyze_document).analyze(_extraction())

    quotations = [finding.evidence_quotation for finding in result.findings]
    assert VISIBLE_RETURN not in quotations
    assert RESTOCKING in quotations
    assert DAMAGE in quotations
    assert result.price is not None
    assert result.price.tax_included is False
    assert result.price.listed_price == "120.00"
    assert result.price.price_with_tax == "130.20"
    assert str(result.price.source_url).rstrip("/") == RETURNS_URL


def test_analyze_drops_quotations_that_are_not_in_the_documents():
    def analyze_document(text: str) -> dict[str, str]:
        if text == DAMAGE:
            return {
                "CancellationTrap": "This membership renews forever and cannot be cancelled.",
                "DamagePolicy": DAMAGE,
            }
        return {}

    result = FinePrintAnalyzer(analyze_document=analyze_document).analyze(_extraction())

    assert [finding.evidence_quotation for finding in result.findings] == [DAMAGE]
    assert result.price is None


def test_analyze_skips_the_tax_price_when_the_page_already_shows_it():
    extraction = _extraction().model_copy(
        update={"page_text": "Alpine Jacket. Price $130.20 including tax."}
    )

    def analyze_document(text: str) -> dict[str, str]:
        if "including tax" in text:
            return {"ListedPrice": "$120"}
        return _analyze_document(text)

    result = FinePrintAnalyzer(analyze_document=analyze_document).analyze(extraction)

    assert result.price is None


def test_env_file_supplies_azure_document_intelligence_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://example.cognitiveservices.azure.com"\n'
        "AZURE_DOCUMENT_INTELLIGENCE_KEY=local-test-key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)

    _load_env_file(env_file)

    assert (
        os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
        == "https://example.cognitiveservices.azure.com"
    )
    assert os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"] == "local-test-key"
