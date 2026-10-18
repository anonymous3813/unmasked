"""The agent stays on product pages and retrieves only what it can source."""

from backend.app.services.claim_validation.analysis import recommend_alternatives
from backend.app.services.catalog.dossier import build_dossier, product_brief
from backend.app.services.catalog.page import accepts_page, is_product_url
from backend.app.services.shop.marks import page_report

PAGE = """Alpine Jacket
Sold by Northwind Outfitters.
Customers say the cuffs stay dry, but one reviewer gave it 3 out of 5 stars after the zipper snagged.
Material: recycled wool
"""


def test_search_and_articles_are_not_product_pages():
    assert is_product_url("https://www.amazon.com/dp/B000000000")
    assert is_product_url("https://www.walmart.com/ip/Alpine-Jacket/123")
    assert not is_product_url("https://www.walmart.com/search?q=jacket")
    assert not accepts_page("https://en.wikipedia.org/wiki/Jacket", product_page=True)
    assert not accepts_page("https://www.google.com/search?q=jacket", product_page=True)


def test_a_non_product_is_not_analyzed():
    report = page_report("https://en.wikipedia.org/wiki/Jacket", product_page=True)

    assert report["active"] is False
    assert report["notes"] == []
    assert report["dossier"]["reviews"] == []


def test_dossier_keeps_the_seller_review_document_and_spec():
    dossier = build_dossier(
        "https://shop.example/products/alpine-jacket",
        PAGE,
        {
            "name": "Alpine Jacket",
            "documents": [
                {
                    "title": "Warranty document",
                    "url": "https://shop.example/pages/warranty",
                    "excerpt": "The warranty excludes damage from normal wear after the first year of use.",
                    "kind": "warranty",
                }
            ],
        },
        search=lambda query: [
            {
                "title": "Alpine Jacket review",
                "url": "https://reviews.example/alpine-jacket",
                "content": "Reviewers say the Northwind Alpine Jacket zipper snagged. 3 out of 5 stars.",
            },
            {
                "title": "Unrelated coat",
                "url": "https://reviews.example/other-coat",
                "content": "Reviewers liked a different coat. 5 stars.",
            },
            {
                "title": "Rab Microlight Alpine Jacket Review",
                "url": "https://reviews.example/rab-alpine-jacket",
                "content": "Rab warranty covers the Alpine Jacket zipper for the original owner.",
            },
        ],
    )

    assert dossier["seller"]["name"] == "Northwind Outfitters"
    assert "3 out of 5" in dossier["reviews"][0]["quote"]
    assert any(review["url"] == "https://reviews.example/alpine-jacket" for review in dossier["reviews"])
    assert all("other-coat" not in review["url"] for review in dossier["reviews"])
    assert all("rab-alpine-jacket" not in item.get("url", "") for item in dossier["reviews"] + dossier["documents"])
    assert dossier["documents"][0]["title"] == "Warranty document"
    assert dossier["specs"] == [{"label": "Material", "value": "recycled wool"}]


def test_brief_uses_only_retrieved_seller_reviews_and_policies():
    brief = product_brief(
        "Alpine Jacket",
        {"seller": {"detail": "Sold by Northwind Outfitters"}, "reviews": [{"quote": "The cuffs stayed dry."}]},
        [{"title": "Return limit", "message": "Returns within the first week if unworn."}],
    )

    assert "Sold by Northwind Outfitters" in brief
    assert "The cuffs stayed dry." in brief
    assert "Returns within the first week" in brief
    assert "No damage policy was retrieved." in brief


def test_greener_and_better_value_products_come_from_the_reviews():
    green = "The Cedar Loop is a better environmental choice at $64.00 because the shell is recycled wool."
    value = "The Plain Loop is the better value at $40.00 for the same warmth."

    def search(query: str):
        if "environment" in query:
            return [{"url": "https://reviews.example/green", "title": "Green", "content": green}]
        return [{"url": "https://reviews.example/value", "title": "Value", "content": value}]

    def complete(_prompt: str) -> str:
        return (
            '{"recommendations": ['
            '{"product_name": "Cedar Loop", "aspect": "environmental", "reason": "Recycled wool shell.", '
            '"source_url": "https://reviews.example/green", '
            '"evidence_quotation": "The Cedar Loop is a better environmental choice at $64.00"}, '
            '{"product_name": "Plain Loop", "aspect": "cost_value", "reason": "Lower price for the same warmth.", '
            '"source_url": "https://reviews.example/value", '
            '"evidence_quotation": "The Plain Loop is the better value at $40.00"}, '
            '{"product_name": "Invented Coat", "aspect": "environmental", "reason": "Not in the review.", '
            '"source_url": "https://reviews.example/green", "evidence_quotation": "not in the review"}]}'
        )

    found = recommend_alternatives("Alpine Jacket", search, complete)
    names = [item.product_name for item in found]

    assert names == ["Cedar Loop", "Plain Loop"]
    assert found[0].aspect.value == "environmental"
    assert found[1].price == "40.00"
