"""Retrieved product data is checked against the public registry."""

from backend.app.services.registry.log import for_product, reset


def test_a_product_page_finds_its_registry_rows(monkeypatch):
    reset()
    rows = [
        {
            "id": "R0002",
            "kind": "page",
            "title": "shop.example",
            "detail": "Return limit",
            "url": "https://www.shop.example/products/alpine-jacket?ref=home",
            "at": "2026-10-18T00:00:00+00:00",
        },
        {
            "id": "R0001",
            "kind": "ask",
            "title": "What is the return policy?",
            "detail": "Alpine Jacket can be returned within 14 days.",
            "url": "https://other.example/products/coat",
            "at": "2026-10-17T00:00:00+00:00",
        },
    ]
    monkeypatch.setattr("backend.app.integrations.supabase_store.load_entries", lambda: rows)

    found = for_product("https://shop.example/products/alpine-jacket", "Alpine Jacket")

    assert [entry["id"] for entry in found] == ["R0002", "R0001"]
    assert "ballot" not in found[0]


def test_an_unrelated_page_does_not_pull_the_registry(monkeypatch):
    reset()
    monkeypatch.setattr(
        "backend.app.integrations.supabase_store.load_entries",
        lambda: [
            {
                "id": "R0009",
                "kind": "page",
                "title": "Other store",
                "detail": "No shared product name here.",
                "url": "https://other.example/products/lamp",
                "at": "2026-10-18T00:00:00+00:00",
            }
        ],
    )

    assert for_product("https://shop.example/products/alpine-jacket", "Alpine Jacket") == []
