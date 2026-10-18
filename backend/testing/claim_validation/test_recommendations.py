"""Recommend other products from review evidence on cost, environment, and durability."""

import json

from backend.app.models.claim_validation import ClaimVerdict, ComparisonAspect, ProductClaim
from backend.app.services.claim_validation.analysis import ClaimAnalysisService

CLAIM = ProductClaim(
    claim_text="The shell is waterproof and guaranteed for life.",
    product_name="Alpine Jacket",
    source_url="https://shop.example/products/jacket",
    category="absolute",
)
LEAK = {
    "title": "Rain test",
    "url": "https://reviews.example/alpine-jacket",
    "content": "The jacket leaked within an hour in steady rain.",
}
ALTERNATIVE = {
    "title": "Jacket comparison",
    "url": "https://shop.example/products/ridge-coat",
    "content": (
        "The Ridge Coat uses recycled polyester and is a better value "
        "than the Alpine Jacket. It costs $90.00."
    ),
    "image": "https://images.example/ridge-coat.jpg",
}


def test_recommends_products_the_reviews_support():
    queries: list[str] = []

    def search(query: str) -> list[dict]:
        queries.append(query)
        if CLAIM.claim_text in query:
            return [LEAK]
        if any(phrase in query for phrase in ("environmentally friendly", "best value", "durable")):
            return [ALTERNATIVE]
        return []

    def complete(prompt: str) -> str:
        if "Recommend alternative products" in prompt:
            assert "contradicted" in prompt
            assert "Ridge Coat uses recycled polyester" in prompt
            return json.dumps(
                {
                    "recommendations": [
                        {
                            "product_name": "Ridge Coat",
                            "aspect": "environmental",
                            "reason": "Reviewers say it uses recycled polyester.",
                            "source_url": ALTERNATIVE["url"],
                            "evidence_quotation": "The Ridge Coat uses recycled polyester",
                        },
                        {
                            "product_name": "Ridge Coat",
                            "aspect": "cost_value",
                            "reason": "The same review calls it a better value than the Alpine Jacket.",
                            "source_url": ALTERNATIVE["url"],
                            "evidence_quotation": "is a better value than the Alpine Jacket.",
                        },
                        {
                            "product_name": "Ghost Jacket",
                            "aspect": "durability",
                            "reason": "Invented.",
                            "source_url": ALTERNATIVE["url"],
                            "evidence_quotation": "The Ghost Jacket never wears out.",
                        },
                        {
                            "product_name": "Alpine Jacket",
                            "aspect": "cost_value",
                            "reason": "This is the product already being checked.",
                            "source_url": ALTERNATIVE["url"],
                            "evidence_quotation": "than the Alpine Jacket.",
                        },
                    ]
                }
            )
        return json.dumps(
            {
                "verdict": "contradicted",
                "explanation": "A review says the jacket leaked within an hour in steady rain.",
            }
        )

    analysis = ClaimAnalysisService(search=search, complete=complete).analyze([CLAIM])

    assert analysis.product_name == "Alpine Jacket"
    assert analysis.validations[0].verdict is ClaimVerdict.CONTRADICTED
    assert {item.aspect for item in analysis.recommendations} == {
        ComparisonAspect.ENVIRONMENTAL,
        ComparisonAspect.COST_VALUE,
    }
    assert {item.product_name for item in analysis.recommendations} == {"Ridge Coat"}
    listing = analysis.recommendations[0]
    assert listing.price == "90.00"
    assert str(listing.product_url).rstrip("/") == ALTERNATIVE["url"]
    assert str(listing.image_url).rstrip("/") == ALTERNATIVE["image"]
    assert any("environmentally friendly" in query for query in queries)
    assert any("best value" in query for query in queries)
    assert any("durable" in query for query in queries)


def test_skips_recommendations_when_no_alternatives_are_found():
    def search(query: str) -> list[dict]:
        if CLAIM.claim_text in query:
            return [LEAK]
        return []

    def complete(prompt: str) -> str:
        if "Recommend alternative products" in prompt:
            raise AssertionError("recommendations should wait until alternative reviews exist")
        return json.dumps(
            {"verdict": "contradicted", "explanation": "A review says the jacket leaked."}
        )

    analysis = ClaimAnalysisService(search=search, complete=complete).analyze([CLAIM])

    assert analysis.validations[0].verdict is ClaimVerdict.CONTRADICTED
    assert analysis.recommendations == []


def test_skips_a_listing_without_a_picture_or_price():
    def search(query: str) -> list[dict]:
        if CLAIM.claim_text in query:
            return [LEAK]
        return [
            {
                "title": "Plain comparison",
                "url": "https://reviews.example/plain-coat",
                "content": "The Plain Coat is a better value than the Alpine Jacket.",
            }
        ]

    def complete(prompt: str) -> str:
        if "Recommend alternative products" in prompt:
            return json.dumps(
                {
                    "recommendations": [
                        {
                            "product_name": "Plain Coat",
                            "aspect": "cost_value",
                            "reason": "Reviewers call it a better value.",
                            "source_url": "https://reviews.example/plain-coat",
                            "evidence_quotation": "The Plain Coat is a better value",
                        }
                    ]
                }
            )
        return json.dumps(
            {"verdict": "contradicted", "explanation": "A review says the jacket leaked."}
        )

    analysis = ClaimAnalysisService(search=search, complete=complete).analyze([CLAIM])

    assert analysis.recommendations == []
