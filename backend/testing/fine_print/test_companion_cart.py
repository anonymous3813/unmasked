"""Companion listings appear only when asked, and checkout is remembered."""

from datetime import datetime, timedelta, timezone

from backend.app.models.agent import PastOrder
from backend.app.services.registry.contact import AgentContact
from backend.app.services.registry.log import reset
from backend.app.services.shop.products import find_products, requested_item
from backend.app.services.shop.cart import ASSISTANT_PHONE, orders_answer, purchase, refresh_delivery


def test_eco_chairs_for_a_canopy_search_folding_chairs():
    from backend.app.services.shop.products import paired_item

    kind, prefix = paired_item(
        "find chairs that are environmentally friendly and go with this",
        "Costway 10 x 10 beige event outdoor canopy",
    )

    assert kind == "folding chair"
    assert prefix == "eco friendly"
    assert paired_item("Can I return these?", "Costway canopy") is None
    assert paired_item("Is this environmentally friendly?", "Costway canopy") is None


def test_only_a_find_request_names_a_product():
    assert requested_item("find a mattress that works with this") == "mattress"
    assert requested_item("what mattress goes with this") == "mattress"
    assert requested_item("what goes with this", "Queen Platform Bed Frame") == "mattress"
    assert requested_item("show me pillows that fit this bed") == "pillows"
    assert requested_item("Can I return these?") is None


def test_a_shorter_title_is_still_another_product():
    from backend.app.services.shop.marks import _same_listing, offer_alternatives

    assert (
        _same_listing(
            "Costway 10 x 10 beige event outdoor canopy",
            "https://www.walmart.com/ip/costway/1",
            "Event Outdoor Canopy",
            "https://www.amazon.com/dp/B000CANOPY1",
        )
        is False
    )


def test_compare_keeps_a_listing_whose_title_overlaps_the_page(monkeypatch):
    from backend.app.services.shop.marks import offer_alternatives

    monkeypatch.setattr("backend.app.services.shop.marks._tavily_ready", lambda: True)
    monkeypatch.setattr(
        "backend.app.services.shop.taste.load_taste",
        lambda user_id="shopper": {"brands": [], "colors": [], "avoid": []},
    )
    monkeypatch.setattr("backend.app.services.shop.marks.TavilyClient", lambda: type("Search", (), {"search": lambda *args, **kwargs: []})())

    def listings(*args, **kwargs):
        return [
            {
                "name": "Event Outdoor Canopy",
                "store": "Amazon",
                "price": "79.99",
                "url": "https://www.amazon.com/dp/B000CANOPY1",
                "imageUrl": "https://images.example/canopy.jpg",
                "message": "Polyester canopy.",
            }
        ]

    monkeypatch.setattr("backend.app.services.shop.marks.find_products", listings)
    found = offer_alternatives(
        "Costway 10 x 10 beige event outdoor canopy",
        "https://www.walmart.com/ip/costway/1",
        "Polyester fabric canopy.",
    )

    assert found["products"]
    assert found["products"][0]["name"] == "Event Outdoor Canopy"
    assert found["products"][0]["price"] == "79.99"
    assert found["products"][0]["reviewNote"]
    assert found["products"][0]["footprintLow"] and found["products"][0]["footprintHigh"]


def test_a_broad_search_still_returns_another_store():
    from backend.app.services.shop.products import loose_products

    def search(query):
        return [
            {
                "title": "Eurmax Pop Up Canopy | Amazon.com",
                "url": "https://www.amazon.com/dp/B000CANOPY9",
                "content": "Eurmax pop up canopy $88.00",
                "image": "https://images.example/eurmax.jpg",
            }
        ]

    cards = loose_products("canopy", "https://www.walmart.com/ip/costway/1", search)

    assert cards[0]["store"] == "Amazon"
    assert cards[0]["name"].startswith("Eurmax")
    assert cards[0]["price"] == "88.00"


def test_a_similar_product_is_shown_only_after_a_photo_is_found():
    from backend.app.services.shop.marks import _with_images

    products = [
        {
            "name": "Leather Hamilton Satchel",
            "store": "Walmart",
            "url": "https://www.walmart.com/ip/satchel/9",
            "imageUrl": "",
        },
        {
            "name": "Plain Tote",
            "store": "Target",
            "url": "https://www.target.com/p/tote/2",
            "imageUrl": "",
        },
    ]

    def search(query: str) -> list[dict]:
        if "Satchel" in query:
            return [{"image": "https://images.example/satchel.jpg", "title": "Leather Hamilton Satchel"}]
        return []

    shown = _with_images(products, search)

    assert [item["name"] for item in shown] == ["Leather Hamilton Satchel"]
    assert shown[0]["imageUrl"] == "https://images.example/satchel.jpg"


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

    assert [card["store"] for card in cards] == ["Walmart", "Amazon", "Home Depot"]
    assert cards[0]["price"] == "129.79"
    assert cards[0]["imageUrl"].endswith("selene-queen.jpg")
    assert cards[1]["price"] == "149.00"
    assert cards[2]["imageUrl"] == ""
    assert all(not card["imageUrl"] or card["imageUrl"].startswith("http") for card in cards)


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
    assert found["environment"] == []


def test_retailer_help_text_is_not_kept_as_a_review():
    from backend.app.services.catalog.dossier import outside_evidence

    def search(query: str) -> list[dict]:
        if "review" in query and "reddit.com" not in query:
            return [
                {
                    "title": "Customer reviews",
                    "url": "https://www.walmart.com/reviews/product/1",
                    "content": "Customer reviews help customers decide whether this Costway canopy is right for them.",
                }
            ]
        return []

    found = outside_evidence("Costway Canopy", search)

    assert found["reviews"] == []
    assert "Retailer help text" in found["coverage"]["reviews"]


def test_a_reddit_thread_counts_as_a_review_when_it_names_the_product():
    from backend.app.services.catalog.dossier import outside_evidence

    def search(query: str) -> list[dict]:
        if "reddit.com" in query:
            return [
                {
                    "title": "Honda lawn mower",
                    "url": "https://www.reddit.com/r/lawncare/comments/honda",
                    "content": "The Honda lawn mower has lasted three seasons.",
                }
            ]
        return []

    found = outside_evidence("Honda Lawn Mower", search)

    assert found["reviews"][0]["url"].startswith("https://www.reddit.com/")


def test_a_review_of_this_kind_of_product_is_kept():
    from backend.app.services.catalog.dossier import outside_evidence

    def search(query: str) -> list[dict]:
        if "review" in query and "reddit.com" not in query:
            return [
                {
                    "title": "Best lawn mowers",
                    "url": "https://www.nytimes.com/wirecutter/reviews/lawn-mowers",
                    "content": "This lawn mower stays quieter than the other gas models. 4 out of 5 stars.",
                }
            ]
        return []

    found = outside_evidence("Honda Lawn Mower", search)

    assert found["reviews"][0]["url"].endswith("/lawn-mowers")


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

    assert any("Honda" in query and "lawn mower" in query for query in queries)
    assert not any("carbon" in query for query in queries)
    assert found["environment"] == []


def test_a_screen_reader_blurb_is_not_the_handbag():
    from backend.app.services.catalog.footprint import estimate_footprint
    from backend.app.services.catalog.identity import identify_product, known_kind

    assert known_kind("Michael Kors Women's Hamilton Satchel") == "satchel"
    picked = identify_product(
        "Product summary presents key product information Keyboard shortcut shift + opt + D",
        "Amazon.com: Michael Kors Women's Hamilton Satchel",
        ["Michael Kors Women's Hamilton Satchel"],
        "Color: Silver-tone Hardware, Urbino Leather. Price $208.60",
    )

    assert picked["name"] == "Michael Kors Women's Hamilton Satchel"
    assert picked["kind"] == "satchel"
    estimate = estimate_footprint(picked["name"], "Urbino Leather satchel")
    assert estimate["material"] == "leather"
    assert estimate["low"] == 12
    assert estimate["high"] == 35


def test_the_visible_heading_wins_over_the_first_structured_product():
    from backend.app.services.catalog.identity import identify_product

    picked = identify_product(
        "Dell UltraSharp 27 Monitor",
        "Amazon.com",
        ["Logitech Wireless Mouse", "Dell UltraSharp 27 Monitor"],
        "A 27 inch computer monitor.",
    )

    assert picked["name"] == "Dell UltraSharp 27 Monitor"
    assert picked["kind"] == "monitor"


def test_a_laptop_page_does_not_keep_keyboards():
    from backend.app.services.shop.products import _matches
    from backend.app.services.catalog.identity import accept_kind, known_kind

    from backend.app.services.shop.products import _same_kind
    from backend.app.services.catalog.identity import same_product

    assert known_kind("Omron Blood Pressure Monitor") == "blood pressure monitor"
    assert known_kind("Dell 27 inch Monitor") == "monitor"
    assert same_product("monitor", "blood pressure monitor") is False
    assert _same_kind("monitor", "Omron Blood Pressure Monitor") is False
    assert _same_kind("monitor", "Dell 27 inch Monitor") is True
    assert _same_kind("monitor", "Dell 27 inch Display") is True
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

    from backend.app.services.shop.products import _product_page

    assert _product_page("https://www.bestbuy.com/site/sony-headphones/6505727.p") is True


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


def test_a_welcome_text_opens_an_sms_conversation(monkeypatch):
    from backend.app.integrations.photon_line import send_intro

    monkeypatch.setenv("PHOTON_API_KEY", "pho_sk_test")
    monkeypatch.setenv("PHOTON_PROJECT_ID", "pho_prj_testproject000000000000")
    monkeypatch.setenv("PHOTON_USER_ID", "pho_usr_agent000000000000000001")
    monkeypatch.setenv("PHOTON_SPACE_ID", "")
    calls = []

    def fake(method, path, key, body):
        calls.append((path, body))
        if path.endswith("/users"):
            return 200, {"id": "pho_usr_shopper00000000000001"}, ""
        if path.endswith("/spaces"):
            return 200, {"id": "pho_spc_welcome0000000000001"}, ""
        return 202, {}, ""

    monkeypatch.setattr("backend.app.integrations.photon_line._bearer", fake)
    result = send_intro("Welcome to Unmasked.", "2065550100")

    assert result["sent"] is True
    assert calls[0][1]["handle"] == "+12065550100"
    assert calls[1][1]["participantIds"][0] == "pho_usr_agent000000000000000001"
    assert calls[2][1]["content"]["text"] == "Welcome to Unmasked."


def test_first_text_waits_for_a_photon_2_space(monkeypatch):
    monkeypatch.setenv("PHOTON_API_KEY", "")
    monkeypatch.delenv("PHOTON_AGENT_IMESSAGE_NUMBER", raising=False)
    monkeypatch.delenv("PHOTON_IMESSAGE_USER_ID", raising=False)
    monkeypatch.setattr("backend.app.integrations.photon_line._load_local_env", lambda: None)
    from backend.app.integrations.photon_line import send_intro

    result = send_intro("Alpine Jacket states no return limit. Environmental friendliness is 50 out of 100.")

    assert result["sent"] is False
    assert "Photon SMS" in result["reason"]


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
