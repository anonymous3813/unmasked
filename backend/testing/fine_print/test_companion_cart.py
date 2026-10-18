"""Companion listings appear only when asked, and checkout is remembered."""

from datetime import datetime, timedelta, timezone

from backend.app.models.agent import PastOrder
from backend.app.services.registry.contact import AgentContact
from backend.app.services.registry.log import reset
from backend.app.services.shop.products import find_products, requested_item
from backend.app.services.shop.cart import ASSISTANT_PHONE, orders_answer, purchase, refresh_delivery


def test_only_a_find_request_names_a_product():
    assert requested_item("find a mattress that works with this") == "mattress"
    assert requested_item("what mattress goes with this") == "mattress"
    assert requested_item("what goes with this", "Queen Platform Bed Frame") == "mattress"
    assert requested_item("show me pillows that fit this bed") == "pillows"
    assert requested_item("Can I return these?") is None


def test_listings_keep_one_priced_product_from_each_store():
    def search(query: str) -> list[dict]:
        assert "mattress" in query
        return [
            {
                "title": "Queen Mattress Protector - Walmart.com",
                "url": "https://www.walmart.com/ip/protector/1",
                "content": "Soft cover $26.99",
            },
            {
                "title": "Selene Queen Mattress - Walmart.com",
                "url": "https://www.walmart.com/ip/Selene-Queen-Mattress/2",
                "content": "Current price $129.79",
                "raw_content": "https://i5.walmartimages.com/seo/selene-queen.jpg",
            },
            {
                "title": "Avenco Queen Mattress 12 Inch",
                "url": "https://www.amazon.com/dp/B0C2BWNL11",
                "content": "Price $149.00",
                "image": "https://m.media-amazon.com/images/avenco.jpg",
            },
            {
                "title": "Plain Queen Mattress",
                "url": "https://www.homedepot.com/p/plain-queen/3",
                "content": "Queen mattress $199.00",
            },
        ]

    cards = find_products(
        "mattress",
        "Queen Platform Bed Frame",
        "Queen size. No box spring.",
        "https://www.wayfair.com/furniture/bed",
        search,
    )

    assert [card["store"] for card in cards] == ["Walmart", "Amazon"]
    assert cards[0]["price"] == "129.79"
    assert cards[0]["imageUrl"].endswith("selene-queen.jpg")
    assert cards[1]["price"] == "149.00"
    assert all(card["imageUrl"].startswith("http") for card in cards)


def test_a_lawn_mower_search_keeps_lawn_mowers():
    def search(query: str) -> list[dict]:
        assert "lawn mower" in query
        return [
            {
                "title": "Greenworks 40V Lawn Mower",
                "url": "https://www.walmart.com/ip/greenworks-mower/1",
                "content": "Cordless lawn mower $299.00",
                "image": "https://i5.walmartimages.com/mower.jpg",
            },
            {
                "title": "Dollhouse Miniature Lawn Mower Kit",
                "url": "https://www.etsy.com/listing/dollhouse-mower/3",
                "content": "Miniature lawn mower for a dollhouse. $18.00",
                "image": "https://i.etsystatic.com/doll-mower.jpg",
            },
            {
                "title": "Garden Hose 50 ft",
                "url": "https://www.amazon.com/dp/B000HOSE11",
                "content": "Use this hose with a lawn mower. $29.00",
                "image": "https://m.media-amazon.com/images/hose.jpg",
            },
        ]

    cards = find_products(
        "lawn mower",
        "Honda Lawn Mower",
        "",
        "https://www.homedepot.com/p/honda-mower/9",
        search,
    )

    assert [card["name"] for card in cards] == ["Greenworks 40V Lawn Mower"]


def test_outside_evidence_comes_from_other_sites():
    from backend.app.services.catalog.dossier import outside_evidence

    def search(query: str) -> list[dict]:
        if "review" in query:
            return [
                {
                    "title": "Wirecutter review",
                    "url": "https://www.nytimes.com/wirecutter/reviews/honda-lawn-mower",
                    "content": "The Honda lawn mower review says the deck is loud. 4 out of 5 stars.",
                }
            ]
        if "carbon" in query:
            return [
                {
                    "title": "Materials note",
                    "url": "https://example.com/honda-mower-carbon",
                    "content": "The Honda lawn mower carbon footprint is 42 kg CO2e because the housing is plastic.",
                }
            ]
        return []

    found = outside_evidence("Honda Lawn Mower", search)

    assert found["reviews"][0]["url"].startswith("https://www.nytimes.com/")
    assert "42 kg" in found["environment"][0]["text"]


def test_a_long_model_title_still_searches_the_brand_and_kind():
    from backend.app.services.catalog.dossier import outside_evidence
    from backend.app.services.catalog.identity import known_kind

    assert known_kind("ZX-9000 Quantum HDR Smart Series") == ""

    queries = []

    def search(query: str) -> list[dict]:
        queries.append(query)
        if "carbon" in query:
            return [
                {
                    "title": "Generic mower study",
                    "url": "https://example.com/generic-mower-carbon",
                    "content": "A gasoline push mower use phase is 173 kg CO2 eq.",
                },
                {
                    "title": "Honda mower footprint",
                    "url": "https://example.com/honda-hrx-carbon",
                    "content": "The Honda lawn mower carbon footprint is 42 kg CO2e.",
                },
            ]
        return []

    found = outside_evidence("Honda HRX217VKA 21 in. Lawn Mower, Smart Drive", search)

    assert any("Honda" in query and "lawn mower" in query and "carbon" in query for query in queries)
    assert len(found["environment"]) == 1
    assert "42 kg" in found["environment"][0]["text"]
    assert "173" not in found["environment"][0]["text"]


def test_a_laptop_page_does_not_keep_keyboards():
    from backend.app.services.shop.products import _matches
    from backend.app.services.catalog.identity import accept_kind, known_kind

    assert known_kind("Dell XPS Laptop with backlit keyboard") == "laptop"
    assert known_kind("Keychron Wireless Keyboard") == "keyboard"
    assert _matches("board", "mechanical keyboard") is False
    assert accept_kind("Speckled Mug", "A ceramic mug.", "keyboard") == ""
    assert accept_kind("Samsung QN65", "A 65 inch television.", "television") == "television"

    def search(query: str) -> list[dict]:
        assert "laptop" in query
        assert "keyboard" not in query
        return [
            {
                "title": "Mechanical Keyboard",
                "url": "https://www.amazon.com/dp/KEY1234567",
                "content": "Keyboard $49.00",
                "image": "https://example.com/keyboard.jpg",
            },
            {
                "title": "Lenovo IdeaPad Laptop",
                "url": "https://www.walmart.com/ip/lenovo-laptop/9",
                "content": "Laptop $499.00",
                "image": "https://example.com/laptop.jpg",
            },
        ]

    cards = find_products(
        "laptop",
        "Dell XPS Laptop with backlit keyboard",
        "",
        "https://www.bestbuy.com/site/dell-xps/p/1",
        search,
    )

    assert [card["name"] for card in cards] == ["Lenovo IdeaPad Laptop"]


def test_the_agent_names_a_kind_the_title_does_not_spell():
    from backend.app.services.catalog.identity import kind_from_model

    def complete(prompt: str) -> str:
        assert "QN65Q60C" in prompt
        return '{"kind": "smart television"}'

    assert kind_from_model("Samsung QN65Q60C 65-Inch QLED", "A 65 inch television.", complete) == "television"


def test_wishlist_saves_and_reports_the_photon_result(monkeypatch):
    from backend.app.services.shop.wishlist import add_wishlist

    monkeypatch.setattr(
        "backend.app.integrations.photon_line.send_intro",
        lambda text: {"sent": False, "reason": "Add a Photon 2.0 API key, agent user, and space so the first text can be delivered."},
    )
    result = add_wishlist(
        {
            "name": "Greenworks 40V Lawn Mower",
            "url": "https://www.walmart.com/ip/greenworks-mower/1",
            "store": "Walmart",
            "price": "299.00",
        }
    )

    assert result["saved"] is True
    assert "wishlist" in result["answer"]
    assert "Photon 2.0" in result["answer"]


def test_checkout_is_remembered_across_stores():
    shopper = AgentContact()
    result = purchase(
        [
            {
                "name": "Selene Queen Mattress",
                "url": "https://www.walmart.com/ip/Selene-Queen-Mattress/2",
                "store": "Walmart",
                "price": "129.79",
            },
            {
                "name": "Avenco Queen Mattress",
                "url": "https://www.amazon.com/dp/B0C2BWNL11",
                "store": "Amazon",
                "price": "149.00",
            },
        ],
        shopper,
    )

    reply = orders_answer("what are my orders", shopper)
    assert "Walmart" in reply
    assert "Amazon" in reply
    assert "Selene Queen Mattress" in reply
    assert "A0001" in reply
    assert result["orders"][0]["store"] == "Walmart"
    assert shopper.profile("shopper").phone_number == ASSISTANT_PHONE
    assert orders_answer("Can I return these?", shopper) is None


def test_delivery_status_advances_and_texts_once_per_change():
    reset()
    shopper = AgentContact()
    shopper.open_profile("shopper", "+15551212000")
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    for order_id, name, score in (("A0001", "Aqua Loop", 80), ("A0002", "Plain Mist", 40)):
        shopper.add_order(
            "shopper",
            PastOrder(
                order_id=order_id,
                product_name=name,
                product_url="https://www.walmart.com/ip/aqua/1",
                ordered_at=now,
                store="Walmart",
                price="24.00",
                environment_score=score,
                materials="recycled wool",
            ),
        )
    sent = []

    def send(text: str) -> dict:
        sent.append(text)
        return {"sent": True}

    placed = refresh_delivery(now, shopper, send)
    moving = refresh_delivery(now + timedelta(minutes=6), shopper, send)
    repeat = refresh_delivery(now + timedelta(minutes=6), shopper, send)
    delivered = refresh_delivery(now + timedelta(minutes=9), shopper, send)

    assert placed["footprint"] == 60
    assert placed["orders"][0]["status"] == "Placed"
    assert moving["orders"][0]["status"] == "Out for delivery"
    assert repeat["orders"][0]["status"] == "Out for delivery"
    assert delivered["orders"][1]["status"] == "Delivered"
    assert len(sent) == 6
    assert "Aqua Loop is placed." in sent[0]


def test_first_text_waits_for_a_photon_2_space(monkeypatch):
    monkeypatch.setenv("PHOTON_API_KEY", "")
    from backend.app.integrations.photon_line import send_intro

    result = send_intro("Alpine Jacket states no return limit. Environmental friendliness is 50 out of 100.")

    assert result["sent"] is False
    assert "Photon 2.0" in result["reason"]


def test_inbox_message_and_call_use_the_cart_and_orders():
    from backend.app.services.shop.inbox import place_call, send_message

    shopper = AgentContact()
    purchase(
        [
            {
                "name": "Selene Queen Mattress",
                "url": "https://www.walmart.com/ip/Selene-Queen-Mattress/2",
                "store": "Walmart",
                "price": "129.79",
            }
        ],
        shopper,
    )
    cart = [{"name": "Avenco Queen Mattress", "store": "Amazon", "price": "149.00"}]

    message = send_message("what are my orders", cart, shopper, complete=lambda prompt: '{"answer": "unused"}')
    call = place_call(
        cart,
        shopper,
        notes=[{"title": "Return limit", "message": "Returns within the first week if unworn."}],
    )

    assert "Selene Queen Mattress" in message["answer"]
    assert "Walmart" in message["answer"]
    assert "Avenco Queen Mattress" in call["summary"]
    assert "first week" in call["summary"]
    assert "Selene Queen Mattress" in call["summary"]
    assert call["inbox"]["calls"]
