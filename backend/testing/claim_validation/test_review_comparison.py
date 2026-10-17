"""Tavily review search and comparison against a seller claim."""

import json

from backend.app.models.claim_validation import ClaimVerdict, ProductClaim
from backend.app.services.claim_validation.validation import ClaimValidationService

CLAIM = ProductClaim(
    claim_text="The shell is waterproof and guaranteed for life.",
    product_name="Alpine Jacket",
    source_url="https://shop.example/products/jacket",
    category="absolute",
)
REVIEW = {
    "title": "Rain test",
    "url": "https://reviews.example/alpine-jacket",
    "content": "The jacket leaked within an hour in steady rain.",
}


def test_contradicts_a_claim_when_reviews_disagree():
    def search(query: str) -> list[dict]:
        assert "Alpine Jacket" in query
        assert "reviews" in query
        assert CLAIM.claim_text in query
        return [REVIEW]

    def complete(prompt: str) -> str:
        assert CLAIM.claim_text in prompt
        assert "leaked within an hour" in prompt
        return json.dumps(
            {
                "verdict": "contradicted",
                "explanation": "A review says the jacket leaked within an hour in steady rain.",
            }
        )

    result = ClaimValidationService(search=search, complete=complete).validate(CLAIM)

    assert result.verdict is ClaimVerdict.CONTRADICTED
    assert "leaked" in result.explanation
    assert result.evidence[0].title == "Rain test"
    assert result.evidence[0].quotation == REVIEW["content"]
    assert str(result.evidence[0].source_url).rstrip("/") == REVIEW["url"]


def test_is_inconclusive_when_no_reviews_are_found():
    def complete(prompt: str) -> str:
        raise AssertionError("comparison should wait until reviews exist")

    result = ClaimValidationService(search=lambda query: [], complete=complete).validate(CLAIM)

    assert result.verdict is ClaimVerdict.INCONCLUSIVE
    assert result.evidence == []
