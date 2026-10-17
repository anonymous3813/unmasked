"""Semantic risk analysis for extracted policy documents."""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from pathlib import Path

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


class AzureDocumentIntelligenceClient:
    """Query-field analysis through Azure Document Intelligence.

    The layout model extracts the policy and price fields used by fine-print
    analysis. Configure ``AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`` and
    ``AZURE_DOCUMENT_INTELLIGENCE_KEY``.
    """

    endpoint_env = "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"
    key_env = "AZURE_DOCUMENT_INTELLIGENCE_KEY"
    api_version = "2024-11-30"
    model_id = "prebuilt-layout"

    def analyze_document(self, text: str) -> dict[str, str]:
        """Extract semantic query fields from one document's text."""
        _load_local_env()
        endpoint = os.environ.get(self.endpoint_env, "").strip().rstrip("/")
        key = os.environ.get(self.key_env)
        if not endpoint or not key:
            raise RuntimeError(
                "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY are required"
            )

        html = f"<html><body><pre>{escape(text)}</pre></body></html>".encode()
        body = json.dumps(
            {"base64Source": base64.b64encode(html).decode("ascii")}
        ).encode()
        query = urllib.parse.urlencode(
            {
                "_overload": "analyzeDocument",
                "api-version": self.api_version,
                "features": "queryFields",
                "queryFields": ",".join(_QUERY_FIELDS),
            }
        )
        url = (
            f"{endpoint}/documentintelligence/documentModels/"
            f"{self.model_id}:analyze?{query}"
        )
        status, headers, _payload = _azure_request(url, key, body, "POST")
        if status != 202:
            raise RuntimeError(
                f"Azure Document Intelligence request failed with status {status}"
            )
        operation = headers.get("Operation-Location")
        if not operation:
            raise RuntimeError("Azure Document Intelligence did not return a result URL")
        return _query_field_values(_poll_result(operation, key))


class FinePrintAnalyzer:
    """Find policy concerns and the tax-inclusive price the product page hides.

    Azure Document Intelligence reads each extracted document for return
    limits, fees, cancellation terms, warranty exclusions, damage liability,
    the listed price, and any stated tax rate. A concern is kept only when
    its quotation is in the source text and is not already on the product page.
    """

    def __init__(self, analyze_document=None) -> None:
        self._analyze_document = analyze_document

    def analyze(self, extraction: FinePrintExtraction) -> FinePrintAnalysisResult:
        """Return buried policy concerns and the tax-inclusive price."""
        analyze_document = (
            self._analyze_document or AzureDocumentIntelligenceClient().analyze_document
        )
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


def _load_local_env() -> None:
    """Load backend/.env without overriding variables already set in the shell."""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_file(env_path)
        return
    load_dotenv(env_path, override=False)


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _poll_result(operation_url: str, key: str) -> dict:
    for _attempt in range(20):
        _status, headers, payload = _azure_request(operation_url, key, None, "GET")
        if payload.get("status") == "succeeded":
            return payload
        if payload.get("status") == "failed":
            raise RuntimeError("Azure Document Intelligence analysis failed")
        retry_after = headers.get("Retry-After")
        time.sleep(float(retry_after) if retry_after else 2)
    raise RuntimeError("Azure Document Intelligence analysis timed out")


def _query_field_values(payload: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for document in (payload.get("analyzeResult") or {}).get("documents") or []:
        for name, field in (document.get("fields") or {}).items():
            if not isinstance(field, dict):
                continue
            content = field.get("content") or field.get("valueString") or ""
            if isinstance(content, str) and content.strip():
                values[name] = content.strip()
    return values


def _azure_request(url: str, key: str, body: bytes | None, method: str) -> tuple[int, dict, dict]:
    headers = {"Ocp-Apim-Subscription-Key": key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            parsed = json.loads(raw.decode()) if raw else {}
            return response.status, dict(response.headers), parsed
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Azure Document Intelligence request failed with status {exc.code}"
        ) from exc


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
