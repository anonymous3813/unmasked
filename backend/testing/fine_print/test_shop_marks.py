"""On-page marks built from a product page and its policy documents."""

from datetime import datetime, timezone

from backend.app.models.fine_print import FinePrintExtraction, PolicyDocument
from backend.app.services.shop_marks import collect_visits, notes_from_page

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


def test_hidden_return_and_listed_price_become_marks():
    notes = notes_from_page(_extraction("Men's Tree Runner. Final few."), "100")

    price = next(note for note in notes if note["kind"] == "price")
    concern = next(note for note in notes if note["kind"] == "concern")
    assert price["listedPrice"] == "100.00"
    assert "does not include tax" in price["message"]
    assert concern["title"] == "Return limit"
    assert "unworn items" in concern["message"]
    assert all("privacy" not in note["message"] for note in notes)


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

    assert [note["kind"] for note in notes] == ["price"]
