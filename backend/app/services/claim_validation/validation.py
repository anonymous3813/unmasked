"""Comparison of seller claims with independent reviews."""

import json
from datetime import datetime, timezone

from backend.app.integrations.gemini_client import GeminiClient
from backend.app.models.claim_validation import (
    ClaimEvidence,
    ClaimValidationResult,
    ClaimVerdict,
    ProductClaim,
)
from backend.app.services.claim_validation.tavily_search import TavilySearchService

_VERDICTS = {verdict.value: verdict for verdict in ClaimVerdict}


class ClaimValidationService:
    """Compare a seller's claim with reviews found through Tavily.

    Gemini reads the claim and the review snippets and returns supported,
    contradicted, or inconclusive. With no reviews, the result is inconclusive
    and Gemini is not called.
    """

    def __init__(self, search=None, complete=None) -> None:
        self._reviews = TavilySearchService(search=search)
        self._complete = complete

    def validate(self, claim: ProductClaim) -> ClaimValidationResult:
        """Search reviews and compare them with one seller claim."""
        evidence = self._reviews.reviews(claim)
        validated_at = datetime.now(timezone.utc)
        if not evidence:
            return ClaimValidationResult(
                claim=claim,
                verdict=ClaimVerdict.INCONCLUSIVE,
                explanation="No independent reviews were found for this claim.",
                evidence=[],
                validated_at=validated_at,
            )

        complete = self._complete or GeminiClient().complete
        verdict, explanation = _comparison(complete(_prompt(claim, evidence)))
        return ClaimValidationResult(
            claim=claim,
            verdict=verdict,
            explanation=explanation,
            evidence=evidence,
            validated_at=validated_at,
        )


def _prompt(claim: ProductClaim, evidence: list[ClaimEvidence]) -> str:
    reviews = "\n\n".join(
        f"Title: {item.title}\nURL: {item.source_url}\nReview: {item.quotation}"
        for item in evidence
    )
    return (
        "Compare the seller claim with the reviews. "
        "Choose supported when the reviews agree with the claim, "
        "contradicted when they disagree, and inconclusive when they do not settle it. "
        "Do not invent review text.\n"
        "Return JSON: {\"verdict\": \"supported|contradicted|inconclusive\", "
        "\"explanation\": \"why, citing the reviews\"}\n\n"
        f"Product: {claim.product_name}\n"
        f"Seller claim: {claim.claim_text}\n\n"
        f"Reviews:\n{reviews}"
    )


def _comparison(raw: str) -> tuple[ClaimVerdict, str]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return ClaimVerdict.INCONCLUSIVE, "The review comparison was not usable."
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return ClaimVerdict.INCONCLUSIVE, "The review comparison was not usable."
    verdict = _VERDICTS.get(str(payload.get("verdict") or "").lower(), ClaimVerdict.INCONCLUSIVE)
    explanation = str(payload.get("explanation") or "").strip()
    if not explanation:
        explanation = "The reviews do not settle this claim."
    return verdict, explanation
