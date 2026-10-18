"""Inbound texts can use the shopper profile, returns, and product search."""

from backend.app.services.shop.accounts import register, reset, user_by_phone
from backend.app.services.shop.cart import mark_returned, purchase
from backend.app.services.shop.updates import sms_reply


def test_sms_reply_knows_the_shopper_name_and_returns(monkeypatch):
    reset()
    created = register("cara@example.com", "correct-horse", "Cara", "+12065550111")
    user_id = created["account"]["id"]
    purchase(
        [
            {"name": "Alpine Wool Jacket", "url": "https://shop.example/jacket", "price": "80", "store": "Alpine", "brand": "Alpine"},
            {"name": "Trail Runner Shoe", "url": "https://shop.example/shoe", "price": "90", "store": "Trail", "brand": "Trail"},
        ],
        user_id=user_id,
    )
    orders = purchase(
        [{"name": "Cheap Rain Shell", "url": "https://shop.example/rain", "price": "40", "store": "Budget", "brand": "Budget"}],
        user_id=user_id,
    )
    mark_returned(orders["orders"][0]["orderId"], user_id=user_id)

    monkeypatch.setattr(
        "backend.app.services.shop.updates._product_search_answer",
        lambda question, profile: "Live listings: jacket\n\n1. Patagonia\n   Torrentshell\n   $179",
    )
    monkeypatch.setattr(
        "backend.app.services.shop.updates._companion_answer",
        lambda question, profile: "Profile fallback",
    )

    assert user_by_phone("+12065550111")["name"] == "Cara"
    about = sms_reply("what's my name", "+12065550111")
    assert "Cara" in about
    assert "cara@example.com" in about.lower() or "Cara" in about

    returned = sms_reply("what did I return", "+12065550111")
    assert "Cheap Rain Shell" in returned or "Budget" in returned

    found = sms_reply("find me a greener jacket", "+12065550111")
    assert "listings" in found.lower() or "Torrentshell" in found

    # Personal returns stay on the returns path; web "return policies" go to companion.
    monkeypatch.setattr(
        "backend.app.services.shop.updates._companion_answer",
        lambda question, profile: "Web policy summary about rain jackets.",
    )
    policy = sms_reply("compare return policies for rain jackets", "+12065550111")
    assert "Cheap Rain Shell" not in policy
    assert "Web policy summary" in policy
