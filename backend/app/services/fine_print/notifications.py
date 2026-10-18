"""Shopper notifications for fine-print concerns, price, and availability."""

import re

from backend.app.models.fine_print import (
    FinePrintAnalysisResult,
    NotificationKind,
    ProductNotification,
    RiskCategory,
    Severity,
)

_TITLES = {
    RiskCategory.RETURN_RESTRICTION: "Return limit",
    RiskCategory.RESTOCKING_FEE: "Restocking fee",
    RiskCategory.CANCELLATION_TRAP: "Cancellation terms",
    RiskCategory.WARRANTY_EXCLUSION: "Warranty exclusion",
    RiskCategory.DAMAGE_POLICY: "Damage policy",
    RiskCategory.OTHER: "Product concern",
}
_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}
_AVAILABILITY = re.compile(
    r"\b(?:in stock|out of stock|currently unavailable|unavailable|"
    r"back-?ordered|only \d+ left|ships in \d+ days?)\b",
    re.IGNORECASE,
)


class FinePrintNotifier:
    """Build notices from a fine-print analysis.

    Each notice is product information for the shopper: a hidden policy
    concern, the tax-inclusive price, or availability stated on the page.
    Delivery, including calls, is separate.
    """

    def build(self, result: FinePrintAnalysisResult) -> list[ProductNotification]:
        """Return price, concern, and availability notices for one product."""
        notes: list[ProductNotification] = []
        if result.price is not None:
            notes.append(
                ProductNotification(
                    kind=NotificationKind.PRICE,
                    title="Price with tax",
                    message=result.price.explanation,
                    source_url=result.price.source_url,
                    created_at=result.analyzed_at,
                )
            )

        findings = sorted(result.findings, key=lambda finding: _SEVERITY_RANK[finding.severity])
        for finding in findings:
            notes.append(
                ProductNotification(
                    kind=NotificationKind.CONCERN,
                    title=_TITLES[finding.category],
                    message=f"{finding.explanation} {finding.evidence_quotation}",
                    source_url=finding.source_url,
                    created_at=result.analyzed_at,
                    severity=finding.severity,
                )
            )

        availability = _availability_sentence(result.document.extracted_text)
        if availability is not None:
            notes.append(
                ProductNotification(
                    kind=NotificationKind.PRODUCT_INFO,
                    title="Availability",
                    message=availability,
                    source_url=result.document.url,
                    created_at=result.analyzed_at,
                )
            )
        return notes


def _availability_sentence(text: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in sentences:
        if _AVAILABILITY.search(sentence):
            return " ".join(sentence.split())
    return None
