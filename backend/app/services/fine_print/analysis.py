"""Semantic risk analysis for extracted policy documents."""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.app.integrations.gemini_client import GeminiClient
from backend.app.models.fine_print import (
    FinePrintAnalysisResult,
    FinePrintExtraction,
    PolicyDocument,
    PriceWithTax,
    RiskCategory,
    RiskFinding,
    Severity,
)

_QUERY_FIELDS = (
    "ReturnRestriction",
    "RestockingFee",
    "CancellationTrap",
    "WarrantyExclusion",
    "DamagePolicy",
    "ListedPrice",
    "SalesTaxRate",
)
_FIELD_CATEGORIES = {
    "ReturnRestriction": RiskCategory.RETURN_RESTRICTION,
    "RestockingFee": RiskCategory.RESTOCKING_FEE,
    "CancellationTrap": RiskCategory.CANCELLATION_TRAP,
    "WarrantyExclusion": RiskCategory.WARRANTY_EXCLUSION,
    "DamagePolicy": RiskCategory.DAMAGE_POLICY,
}
_FIELD_SEVERITY = {
    RiskCategory.RETURN_RESTRICTION: Severity.MEDIUM,
    RiskCategory.RESTOCKING_FEE: Severity.HIGH,
    RiskCategory.CANCELLATION_TRAP: Severity.HIGH,
    RiskCategory.WARRANTY_EXCLUSION: Severity.MEDIUM,
    RiskCategory.DAMAGE_POLICY: Severity.MEDIUM,
}
_FIELD_EXPLANATIONS = {
    RiskCategory.RETURN_RESTRICTION: "The return terms can limit a refund, and the product page does not show them.",
    RiskCategory.RESTOCKING_FEE: "Opening or using the item can add a restocking fee the product page does not show.",
    RiskCategory.CANCELLATION_TRAP: "Cancellation is harder than the product page shows.",
    RiskCategory.WARRANTY_EXCLUSION: "The warranty leaves out situations the product page does not mention.",
    RiskCategory.DAMAGE_POLICY: "Damage liability can fall on the shopper under terms the product page does not show.",
}
_TAX_INCLUDED_PHRASES = (
    "tax included",
    "including tax",
    "includes tax",
    "incl. tax",
    "incl tax",
    "price with tax",
)


class GeminiFieldReader:
    """Read policy and price fields with Gemini.

    Gemini quotes return limits, fees, cancellation terms, warranty exclusions,
    damage liability, the listed price, and any stated tax rate. Configure
    ``GEMINI_API_KEY`` in the environment or ``backend/.env``.
    """

    def __init__(self, complete=None) -> None:
        self._complete = complete

    def analyze_document(self, text: str) -> dict[str, str]:
        """Return exact quotations for the fine-print fields found in one text."""
        complete = self._complete or GeminiClient().complete
        return _fields_from_response(complete(_field_prompt(text)), text)


class FinePrintAnalyzer:
    """Find policy concerns and the tax-inclusive price the product page hides.

    Gemini reads each extracted document for return limits, fees, cancellation
    terms, warranty exclusions, damage liability, the listed price, and any
    stated tax rate. A concern is kept only when its quotation is in the
    source text and is not already on the product page.
    """

    def __init__(self, analyze_document=None) -> None:
        self._analyze_document = analyze_document

    def analyze(self, extraction: FinePrintExtraction) -> FinePrintAnalysisResult:
        """Return buried policy concerns and the tax-inclusive price."""
        analyze_document = self._analyze_document or GeminiFieldReader().analyze_document
        fields = _collected_fields(extraction, analyze_document)
        return FinePrintAnalysisResult(
            document=PolicyDocument(
                url=extraction.source_url,
                extracted_text=extraction.page_text,
                retrieved_at=extraction.retrieved_at,
            ),
            findings=_findings(fields, extraction.page_text),
            price=_price(fields, extraction.page_text),
            analyzed_at=datetime.now(timezone.utc),
        )


def _collected_fields(extraction: FinePrintExtraction, analyze_document) -> list[tuple[str, str, str]]:
    collected: list[tuple[str, str, str]] = []
    texts = [(str(extraction.source_url), extraction.page_text)]
    texts.extend((str(document.url), document.extracted_text) for document in extraction.documents)
    for source_url, text in texts:
        raw_fields = analyze_document(text) or {}
        for name, content in raw_fields.items():
            quotation = str(content or "").strip()
            if quotation and _normalize(quotation) in _normalize(text):
                collected.append((str(name), quotation, source_url))
    return collected


def _findings(fields: list[tuple[str, str, str]], page_text: str) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    seen: set[tuple[str, str]] = set()
    for name, quotation, source_url in fields:
        category = _FIELD_CATEGORIES.get(name)
        if category is None or _already_visible(quotation, page_text):
            continue
        key = (category.value, _normalize(quotation))
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            RiskFinding(
                category=category,
                severity=_FIELD_SEVERITY[category],
                explanation=_FIELD_EXPLANATIONS[category],
                evidence_quotation=quotation,
                source_url=source_url,
            )
        )
    return findings


def _price(fields: list[tuple[str, str, str]], page_text: str) -> PriceWithTax | None:
    if _page_shows_tax_inclusive_price(page_text):
        return None

    listed_field = next((field for field in fields if field[0] == "ListedPrice"), None)
    tax_field = next((field for field in fields if field[0] == "SalesTaxRate"), None)
    if listed_field is None:
        return None

    listed = _money(listed_field[1])
    if listed is None:
        return None
    rate = _rate(tax_field[1]) if tax_field else None
    total = None if rate is None else (listed * (Decimal("1") + rate)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    if total is not None and _already_visible(f"{total:.2f}", page_text):
        return None

    evidence_quotation, source_url = tax_field[1:] if tax_field else listed_field[1:]
    if total is None:
        explanation = (
            f"The page shows USD {listed:.2f}. "
            "That price does not include tax, and no tax rate is stated, "
            "so the checkout total will be higher."
        )
    else:
        explanation = (
            f"The page shows USD {listed:.2f}. "
            f"Sales tax of {tax_field[1]} is not included. "
            f"With tax, the price is USD {total:.2f}."
        )
    return PriceWithTax(
        listed_price=f"{listed:.2f}",
        currency="USD",
        tax_included=False,
        price_with_tax=None if total is None else f"{total:.2f}",
        tax_rate=None if tax_field is None else tax_field[1],
        explanation=explanation,
        evidence_quotation=evidence_quotation,
        source_url=source_url,
    )


def _field_prompt(text: str) -> str:
    names = ", ".join(_QUERY_FIELDS)
    return (
        "Extract fine-print fields from the document. "
        f"Use only these keys: {names}. "
        "Each value must be an exact contiguous quotation from the document, "
        "or an empty string when the field is absent. Do not invent text.\n"
        'Return JSON like {"RestockingFee": "exact quote", "ListedPrice": "$120"}.\n\n'
        f"Document:\n{text}"
    )


def _fields_from_response(raw: str, source_text: str) -> dict[str, str]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    fields: dict[str, str] = {}
    normalized_source = _normalize(source_text)
    for name in _QUERY_FIELDS:
        quotation = str(payload.get(name) or "").strip()
        if quotation and _normalize(quotation) in normalized_source:
            fields[name] = quotation
    return fields


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _already_visible(quotation: str, page_text: str) -> bool:
    return _normalize(quotation) in _normalize(page_text)


def _page_shows_tax_inclusive_price(page_text: str) -> bool:
    normalized = _normalize(page_text)
    return any(phrase in normalized for phrase in _TAX_INCLUDED_PHRASES)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _money(value: str) -> Decimal | None:
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _rate(value: str) -> Decimal | None:
    percent = "%" in value
    try:
        number = Decimal(value.replace("%", "").strip())
    except Exception:
        return None
    if percent or number > 1:
        return number / Decimal("100")
    return number
