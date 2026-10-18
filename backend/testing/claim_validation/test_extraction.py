"""Extraction of claims a seller makes about a product."""

from backend.app.services.claim_validation.extraction import ClaimExtractor

PAGE_URL = "https://shop.example/products/jacket"
PAGE = """
# Alpine Jacket
The shell is waterproof and guaranteed for life.
It is the best jacket for rain.
The battery lasts up to 20 hours.
Ships in 5 days.
Returns are accepted within 30 days.
"""


def _extract(text: str = PAGE) -> list:
    return ClaimExtractor(
        fetch=lambda url: "<html></html>",
        extract_html=lambda html: text,
    ).extract(PAGE_URL)


def test_extracts_seller_claims_and_skips_shipping_and_returns():
    claims = _extract()
    texts = [claim.claim_text for claim in claims]

    assert texts == [
        "The shell is waterproof and guaranteed for life.",
        "It is the best jacket for rain.",
        "The battery lasts up to 20 hours.",
    ]
    assert claims[0].category == "absolute"
    assert claims[1].category == "comparative"
    assert claims[2].category == "quantitative"
    assert all(claim.product_name == "Alpine Jacket" for claim in claims)
    assert all(str(claim.source_url).rstrip("/") == PAGE_URL for claim in claims)
