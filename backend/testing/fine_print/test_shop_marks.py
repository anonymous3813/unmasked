"""On-page marks built from a product page and its policy documents."""

from datetime import datetime, timezone

from backend.app.models.fine_print import FinePrintExtraction, PolicyDocument
from backend.app.services.shop.marks import (
    _add_review_alternatives,
    collect_visits,
    notes_from_browser,
    notes_from_page,
)

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
PAGE = "https://shop.example/products/jacket"
RETURN = (
    "Our standard return policy is 30 days. "
    "You can return unworn items with the original tags attached."
)


def _extraction(page_text: str) -> FinePrintExtraction:
    return FinePrintExtraction(
        source_url=PAGE,
        page_text=page_text,
        documents=[
            PolicyDocument(url="https://shop.example/pages/returns", extracted_text=RETURN, retrieved_at=NOW),
            PolicyDocument(
                url="https://shop.example/pages/privacy",
                extracted_text="We may share data if you request a refund of your account.",
                retrieved_at=NOW,
            ),
        ],
        retrieved_at=NOW,
    )


def test_hidden_return_and_listed_price_become_marks(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.shop.tax._fetch_zip",
        lambda code: {"places": [{"place name": "Sacramento", "state abbreviation": "CA"}]},
    )
    notes = notes_from_page(
        _extraction("Men's Tree Runner. Final few."),
        "100",
        postal_code="95814",
    )

    price = next(note for note in notes if note["kind"] == "price")
    concern = next(note for note in notes if note["kind"] == "concern")
    assert price["listedPrice"] == "100.00"
    assert price["priceWithTax"] == "108.80"
    assert "Sacramento" in price["label"]
    assert "8.80%" in price["message"]
    assert concern["title"] == "Return limit"
    assert "unworn items" in concern["message"]
    assert all("privacy" not in note["message"] for note in notes)


def test_open_page_text_becomes_a_return_mark():
    notes = notes_from_browser(
        "Alpine Jacket. Returns within the first week if unworn. "
        "The warranty excludes damage from normal wear after the first year of use.",
        "120",
    )

    titles = [note["title"] for note in notes]
    assert titles == ["Return limit", "Warranty exclusion"]
    assert "unworn" in notes[0]["message"]
    assert notes[0]["symbol"] == "↩"


def test_buyer_protection_and_damage_window_become_marks():
    notes = notes_from_browser(
        "15-day buyer protection applies to this order. "
        "Free returns are available if the item is not as described. "
        "Report a damaged item within 48 hours of delivery.",
        "20",
    )

    titles = [note["title"] for note in notes]
    assert titles[0] == "Return limit"
    assert "Damage policy" in titles
    assert "buyer protection" in notes[0]["message"]


def test_review_search_lists_each_website_once():
    visits = collect_visits(
        ["https://www.shop.example/pages/returns"],
        [
            (
                '"Alpine Jacket" reviews waterproof',
                {"url": "https://www.runrepeat.com/alpine", "title": "Alpine review"},
            ),
            (
                '"Alpine Jacket" reviews waterproof',
                {"url": "https://runrepeat.com/alpine?ref=search", "title": "Alpine review again"},
            ),
            (
                '"Alpine Jacket" best value alternatives reviews',
                {"url": "https://outdoorgearlab.com/alpine", "title": "Better jacket"},
            ),
        ],
    )

    assert [(visit["site"], visit["reason"]) for visit in visits] == [
        ("shop.example", "Policy page"),
        ("runrepeat.com", "Reviews of the seller's claim"),
        ("outdoorgearlab.com", "Best value alternatives"),
    ]
    assert visits[1]["title"] == "Alpine review"
    assert visits[1]["url"] == "https://www.runrepeat.com/alpine"


def test_a_return_already_on_the_page_is_not_marked_again():
    notes = notes_from_page(_extraction(f"Tree Runner. {RETURN}"), "100")

    assert notes == []


def test_priced_listings_fill_greener_and_better_value_cards(monkeypatch):
    monkeypatch.setattr("backend.app.services.shop.marks._tavily_ready", lambda: True)
    monkeypatch.setattr("backend.app.services.shop.marks._gemini_ready", lambda: False)

    def listings(item, title="", page_text="", current_url="", search=None, extract=None, query_prefix=""):
        assert item == "shower head"
        if "eco" in query_prefix:
            return [
                {
                    "name": "Aqua Loop Shower Head",
                    "store": "Walmart",
                    "price": "24.00",
                    "url": "https://www.walmart.com/ip/aqua/1",
                    "imageUrl": "",
                    "message": "Recycled low-flow head $24.00",
                }
            ]
        if "reviewed" in query_prefix:
            return [
                {
                    "name": "Rated Mist Shower Head",
                    "store": "Home Depot",
                    "price": "18.00",
                    "url": "https://www.homedepot.com/p/rated-mist/3",
                    "imageUrl": "",
                    "message": "Customers rate this 4 out of 5 stars.",
                }
            ]
        return [
            {
                "name": "Plain Mist Shower Head",
                "store": "Amazon",
                "price": "9.99",
                "url": "https://www.amazon.com/dp/B000TEST11",
                "imageUrl": "",
                "message": "Price $9.99",
            }
        ]

    monkeypatch.setattr("backend.app.services.shop.marks.find_products", listings)
    notes = _add_review_alternatives(
        [],
        "FEELSO Shower Head with Handheld",
        [],
        "https://www.aliexpress.com/item/1.html",
    )

    assert [note["aspect"] for note in notes] == ["environmental", "cost_value", "reviews"]
    assert notes[0]["store"] == "Walmart"
    assert notes[0]["environmentScore"] > 50
    assert notes[0]["productUrl"].startswith("https://www.walmart.com/")
    assert notes[1]["price"] == "9.99"
    assert notes[2]["productName"] == "Rated Mist Shower Head"
