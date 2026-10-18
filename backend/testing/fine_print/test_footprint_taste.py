"""Footprint estimates and taste from orders and receipts."""

from backend.app.services.catalog.footprint import estimate_footprint
from backend.app.services.shop.receipts import add_receipt, read_receipt, reset
from backend.app.services.shop.taste import personalize, profile_from


def test_a_wool_jacket_gets_a_material_estimate_without_a_carbon_document():
    footprint = estimate_footprint("Alpine Jacket", "", [{"label": "Material", "value": "recycled wool"}])

    assert footprint["material"] == "recycled wool"
    assert footprint["low"] and footprint["high"]
    assert "typically about" in footprint["headline"]
    assert "not a measurement" in footprint["detail"]


def test_an_outside_range_replaces_the_table_when_it_names_the_material():
    from backend.app.services.catalog.footprint import with_outside_sources

    estimate = estimate_footprint("Alpine Jacket", "", [{"label": "Material", "value": "wool"}])
    queries = []

    def search(query: str) -> list[dict]:
        queries.append(query)
        return [
            {
                "title": "Wool jacket footprint",
                "url": "https://example.com/wool-jacket",
                "content": "A wool jacket is typically 18 to 40 kg CO2e to manufacture.",
            },
            {
                "title": "Same page",
                "url": "https://shop.example/products/alpine",
                "content": "This wool jacket is 1 to 2 kg CO2e.",
            },
            {
                "title": "Single figure",
                "url": "https://example.com/one-number",
                "content": "The wool jacket carbon footprint is 42 kg CO2e.",
            },
        ]

    sourced = with_outside_sources(estimate, search, "https://shop.example/products/alpine")

    assert "wool jacket carbon footprint kg CO2e" in queries
    assert sourced["low"] == 18
    assert sourced["high"] == 40
    assert sourced["source"]["url"] == "https://example.com/wool-jacket"
    assert "42" not in sourced["headline"]


def test_a_polyester_canopy_gets_a_kilogram_range():
    footprint = estimate_footprint(
        "Costway 10 x 10 beige event outdoor canopy",
        "Waterproof polyester fabric, steel frame, and a double-tier canopy.",
    )

    assert footprint["kind"] == "canopy"
    assert footprint["material"] == "polyester"
    assert footprint["low"] == 15
    assert footprint["high"] == 40
    assert "15–40 kg CO2e" in footprint["productHeadline"]
    assert "did not name a material" not in footprint["detail"]
    assert "42" not in footprint["headline"]


def test_a_jacket_without_a_named_material_uses_a_typical_material():
    footprint = estimate_footprint("Alpine Jacket", "Free shipping on this jacket.", [])

    assert footprint["material"] == "polyester"
    assert footprint["low"] and footprint["high"]
    assert "often made from polyester" in footprint["headline"]
    assert "Alpine" in footprint["headline"]
    assert "company footprint" in footprint["headline"]


def test_kept_brands_and_colors_rank_similar_products():
    taste = profile_from(
        [{"name": "Patagonia Nano Puff Jacket", "materials": "color:navy", "status": "Delivered"}],
        [{"items": [{"name": "Returned Arc'teryx jacket", "returned": True}]}],
    )
    products = personalize(
        [
            {"name": "Arc'teryx Beta Jacket", "url": "https://example.com/a"},
            {"name": "Patagonia Navy Torrentshell Jacket", "url": "https://example.com/b"},
            {"name": "Plain Black Rain Jacket", "url": "https://example.com/c"},
        ],
        taste,
    )

    assert products[0]["name"].startswith("Patagonia")
    assert "patagonia" in products[0]["because"].lower()
    assert all("Arc'teryx" not in product["name"] for product in products)


def test_a_receipt_line_keeps_the_brand_color_and_return():
    reset()
    record = add_receipt("Patagonia Men's Nano Puff Jacket Navy $199.00 returned\n")

    item = record["items"][0]
    assert item["brand"] == "Patagonia"
    assert item["color"] == "navy"
    assert item["returned"] is True
    assert read_receipt("Store\nBlue cotton shirt\n")[0]["color"] == "blue"


def test_an_invoice_keeps_the_products_and_their_prices():
    items = read_receipt(
        "Amazon Business\n"
        "Invoice\n"
        "Cadbury Dairy Milk Giant Buttons Chocolate Bag, 40g\n"
        "1\n"
        "£0.51\n"
        "20%\n"
        "£0.61\n"
        "£0.61\n"
        "ASIN: B01SG2H04C\n"
        "Cadbury Twirl Chocolate Bar, 43g\n"
        "1\n"
        "£0.46\n"
        "20%\n"
        "£0.55\n"
        "£0.55\n"
        "ASIN: B000H4LOFM\n"
        "Shipping Charges\n"
        "£2.99\n"
        "Promotions\n"
        "-£2.99\n"
        "Total\n"
        "£1.16\n"
    )

    assert [item["name"] for item in items] == [
        "Cadbury Dairy Milk Giant Buttons Chocolate Bag, 40g",
        "Cadbury Twirl Chocolate Bar, 43g",
    ]
    assert [item["price"] for item in items] == ["0.61", "0.55"]
    assert items[0]["brand"] == "Cadbury"


def test_claim_words_load_from_the_app_folder():
    from backend.app.services.claim_validation.extraction import ClaimExtractor

    words = ClaimExtractor(fetch=lambda url: "", extract_html=lambda html: "")._keywords
    assert words["comparative"]
    assert words["absolute"]


def test_a_bill_photo_is_read_from_the_image(monkeypatch):
    from backend.app.services.shop.receipts import read_upload

    seen = {}

    def read_image(self, data: bytes, mime: str) -> str:
        seen["mime"] = mime
        seen["size"] = len(data)
        return "Cadbury Twirl Chocolate Bar, 43g £0.55\n"

    monkeypatch.setattr("backend.app.integrations.openai_client.OpenAIClient.read_image", read_image)
    text = read_upload("amazon-bill.jpg", b"\xff\xd8\xff\x00not-text")
    items = read_receipt(text)

    assert seen == {"mime": "image/jpeg", "size": 12}
    assert items[0]["name"] == "Cadbury Twirl Chocolate Bar, 43g"
    assert items[0]["price"] == "0.55"
