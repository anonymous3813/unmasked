"""Claim verdicts plus recommendations drawn from the same review evidence."""

import json
import re
from datetime import datetime, timezone

from backend.app.integrations.gemini_client import GeminiClient
from backend.app.integrations.tavily_client import TavilyClient
from backend.app.models.claim_validation import (
    ClaimAnalysis,
    ClaimEvidence,
    ClaimValidationResult,
    ComparisonAspect,
    ProductClaim,
    ProductRecommendation,
)
from backend.app.services.claim_validation.validation import ClaimValidationService

_ASPECTS = {aspect.value: aspect for aspect in ComparisonAspect}
_PRICE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")
_ASPECT_QUERIES = (
    (ComparisonAspect.ENVIRONMENTAL, "environmentally friendly alternatives"),
    (ComparisonAspect.COST_VALUE, "best value alternatives"),
    (ComparisonAspect.DURABILITY, "durable alternatives"),
)


class ClaimAnalysisService:
    """Check seller claims, then recommend other products the reviews support.

    Each claim is compared with independent reviews. Separate searches look
    for products that reviewers call more environmentally friendly, a better
    cost for the value, or more durable. A recommendation is kept only when
    its quotation appears in a review and names a different product.
    """

    def __init__(self, search=None, complete=None) -> None:
        self._validator = ClaimValidationService(search=search, complete=complete)
        self._search = search
        self._complete = complete

    def analyze(self, claims: list[ProductClaim]) -> ClaimAnalysis:
        """Validate the seller claims and recommend alternatives from reviews."""
        validations = [self._validator.validate(claim) for claim in claims]
        product_name = claims[0].product_name
        analyzed_at = datetime.now(timezone.utc)
        evidence = _alternative_reviews(self._search, product_name)
        if not evidence:
            return ClaimAnalysis(
                product_name=product_name,
                validations=validations,
                recommendations=[],
                analyzed_at=analyzed_at,
            )

        complete = self._complete or GeminiClient().complete
        recommendations = _recommendations(
            complete(_prompt(product_name, validations, evidence)),
            evidence,
            product_name,
        )
        return ClaimAnalysis(
            product_name=product_name,
            validations=validations,
            recommendations=recommendations,
            analyzed_at=analyzed_at,
        )


def recommend_alternatives(product_name: str, search, complete=None) -> list[ProductRecommendation]:
    """Recommend greener and better-value products named by reviews.

    A card is kept only when the review names that other product and a price.
    """
    evidence = _aspect_reviews(search, product_name, _ASPECT_QUERIES[:2])
    if not evidence:
        return []
    complete = complete or GeminiClient().complete
    return [
        item
        for item in _recommendations(complete(_prompt(product_name, [], evidence)), evidence, product_name)
        if item.aspect in {ComparisonAspect.ENVIRONMENTAL, ComparisonAspect.COST_VALUE}
    ]


def _aspect_reviews(search, product_name: str, queries) -> list[ClaimEvidence]:
    search = search or TavilyClient().search
    retrieved_at = datetime.now(timezone.utc)
    seen: set[str] = set()
    evidence: list[ClaimEvidence] = []
    for _aspect, phrase in queries:
        for hit in search(f'"{product_name}" {phrase} reviews'):
            url = str(hit.get("url") or "").strip()
            quotation = str(hit.get("content") or "").strip()
            title = str(hit.get("title") or url).strip()
            image_url = _image_url(hit)
            if not url or not quotation or not title or url in seen:
                continue
            seen.add(url)
            evidence.append(
                ClaimEvidence(
                    source_url=url,
                    title=title,
                    quotation=quotation,
                    retrieved_at=retrieved_at,
                    image_url=image_url,
                )
            )
    return evidence


def _alternative_reviews(search, product_name: str) -> list[ClaimEvidence]:
    return _aspect_reviews(search, product_name, _ASPECT_QUERIES)


def _prompt(
    product_name: str,
    validations: list[ClaimValidationResult],
    evidence: list[ClaimEvidence],
) -> str:
    checked = "\n".join(
        f"- {item.claim.claim_text} ({item.verdict.value}): {item.explanation}"
        for item in validations
    )
    reviews = "\n\n".join(
        f"Title: {item.title}\nURL: {item.source_url}\nReview: {item.quotation}"
        for item in evidence
    )
    aspects = ", ".join(aspect.value for aspect in ComparisonAspect)
    return (
        "Recommend alternative products that these reviews support "
        "as more environmentally friendly, a better cost for the value, or more durable. "
        "Use the claim verdicts when you explain why another product is a better fit. "
        "Copy the product name and a short quotation from the reviews. "
        "Do not recommend the product already being checked, and do not invent products.\n"
        f"Return JSON: {{\"recommendations\": [{{\"product_name\": \"name from the review\", "
        f"\"aspect\": \"{'|'.join(aspects)}\", "
        "\"reason\": \"why this product fits that aspect\", "
        "\"source_url\": \"review url\", "
        "\"evidence_quotation\": \"exact words from that review\"}]}}\n\n"
        f"Product being checked: {product_name}\n"
        f"Claim verdicts:\n{checked}\n\n"
        f"Reviews:\n{reviews}"
    )


def _recommendations(
    raw: str,
    evidence: list[ClaimEvidence],
    product_name: str,
) -> list[ProductRecommendation]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    by_url = {str(item.source_url).rstrip("/"): item for item in evidence}
    kept: list[ProductRecommendation] = []
    for item in payload.get("recommendations") or []:
        if not isinstance(item, dict):
            continue
        aspect = _ASPECTS.get(str(item.get("aspect") or "").lower())
        name = str(item.get("product_name") or "").strip()
        reason = str(item.get("reason") or "").strip()
        quotation = str(item.get("evidence_quotation") or "").strip()
        source = by_url.get(str(item.get("source_url") or "").strip().rstrip("/"))
        if (
            aspect is None
            or not name
            or not reason
            or not quotation
            or source is None
            or name.lower() == product_name.lower()
            or quotation not in source.quotation
            or name.lower() not in source.quotation.lower()
            or _listed_price(source.quotation) is None
        ):
            continue
        kept.append(
            ProductRecommendation(
                product_name=name,
                aspect=aspect,
                reason=reason,
                source_url=source.source_url,
                evidence_quotation=quotation,
                product_url=source.source_url,
                image_url=source.image_url,
                price=_listed_price(source.quotation),
            )
        )
    return kept


def _image_url(hit: dict) -> str | None:
    image = hit.get("image") or hit.get("image_url")
    if not image and isinstance(hit.get("images"), list) and hit["images"]:
        image = hit["images"][0]
    image = str(image or "").strip()
    if image.startswith("https://") or image.startswith("http://"):
        return image
    return None


def _listed_price(text: str) -> str | None:
    match = _PRICE.search(text)
    if match is None:
        return None
    dollars = match.group(1).replace(",", "")
    cents = match.group(2) or "00"
    return f"{dollars}.{cents}"
