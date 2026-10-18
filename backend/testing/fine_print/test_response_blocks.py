"""Shopping reports repeat retrieved evidence and leave gaps empty."""

import json

from backend.app.main import AskRequest, PageNotesRequest, ask, page_notes
from backend.app.services.catalog.report import build_report, clean_report, look_at_page


ALPINE = {
    "name": "Alpine Jacket",
    "seller": {"name": "Northwind Outfitters", "detail": "Sold by Northwind Outfitters", "source": "This page"},
    "reviews": [],
    "documents": [],
    "specs": [{"label": "Material", "value": "recycled wool"}],
}

OUTSIDE_MATERIALS = {
    "reviews": [
        {
            "quote": "Reviewers say the Alpine Jacket zipper snagged.",
            "source": "Alpine Jacket review",
            "url": "https://reviews.example/alpine-jacket",
        }
    ],
    "policies": [],
    "environment": [
        {
            "text": "The Alpine Jacket shell is polyester.",
            "source": "Alpine Jacket materials",
            "url": "https://outside.example/alpine-jacket-materials",
        }
    ],
}


def _blob(report: dict) -> str:
    return json.dumps(report)


def test_materials_do_not_become_a_carbon_number_or_a_score():
    report = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside=OUTSIDE_MATERIALS,
        notes=[{"kind": "recommendation", "environmentScore": 72, "productName": "Other Jacket"}],
        products=[],
    )

    assert report["demo"] is False
    assert "environmentScore" not in _blob(report)
    assert "environment_score" not in _blob(report)
    text = _blob(report).lower()
    assert "kg" not in text
    assert "carbon footprint not verified" in text
    missing = next(block for block in report["blocks"] if block["type"] == "missing_evidence")
    assert missing["metric"] == "product_carbon_footprint"
    sustainability = next(block for block in report["blocks"] if block["type"] == "sustainability_report")
    assert sustainability["status"] == "insufficient_evidence"
    assert any(finding["status"] == "manufacturer_claim" and "recycled wool" in finding["value"] for finding in sustainability["findings"])
    assert len(sustainability["findings"]) <= 3
    assert {block["type"] for block in report["blocks"]} <= {
        "summary_card",
        "sustainability_report",
        "missing_evidence",
        "source_list",
        "suggested_action",
        "follow_up",
    }


def test_a_stated_product_footprint_is_copied_from_the_source():
    report = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside={
            "reviews": [],
            "policies": [],
            "environment": [
                {
                    "text": "The Alpine Jacket lifecycle measurement is 42 kg CO2e.",
                    "source": "Alpine Jacket footprint",
                    "url": "https://outside.example/alpine-jacket-footprint",
                }
            ],
        },
        notes=[],
        products=[],
    )

    assert "42 kg" in _blob(report)
    assert not any(block["type"] == "missing_evidence" for block in report["blocks"])
    sustainability = next(block for block in report["blocks"] if block["type"] == "sustainability_report")
    assert sustainability["status"] == "verified"
    source = next(item for item in report["sources"] if item["url"].endswith("footprint"))
    assert source["productSpecific"] is True
    assert source["sourceClass"] == "independent_product"


def test_a_generic_carbon_article_stays_out_of_the_product_footprint():
    report = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier={"name": "Alpine Jacket", "seller": {}, "reviews": [], "documents": [], "specs": []},
        outside={
            "reviews": [],
            "policies": [],
            "environment": [
                {
                    "text": "A typical jacket can account for 20 kg CO2e.",
                    "source": "Clothing footprint explainer",
                    "url": "https://background.example/clothing-footprints",
                }
            ],
        },
        notes=[],
        products=[],
    )

    assert "20" not in _blob(report)
    assert "carbon footprint not verified" in _blob(report).lower()
    source = report["sources"][0]
    assert source["sourceClass"] == "background"
    assert source["productSpecific"] is False


def test_unknown_blocks_are_dropped():
    cleaned = clean_report(
        {
            "responseId": "example",
            "summary": "Material information is available, but product-level emissions are unverified.",
            "demo": False,
            "blocks": [
                {"type": "summary_card", "verdict": "Emissions are unverified.", "why": "No measurement was found."},
                {"type": "html", "markup": "<script>alert(1)</script>"},
                {"type": "sustainability_report", "title": "Environmental analysis", "status": "nope", "findings": []},
            ],
            "sources": [],
            "suggestedActions": [{"type": "compare_alternatives", "label": "Compare greener alternatives"}],
            "followUps": [],
        }
    )

    assert [block["type"] for block in cleaned["blocks"]] == ["summary_card"]
    assert "<script>" not in _blob(cleaned)


def test_compare_is_offered_only_for_a_pictured_product():
    hidden = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside={"reviews": [], "policies": [], "environment": []},
        notes=[],
        products=[{"name": "Plain Jacket", "url": "https://shop.example/plain", "store": "Shop", "price": "80", "imageUrl": ""}],
    )
    shown = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside={"reviews": [], "policies": [], "environment": []},
        notes=[],
        products=[
            {
                "name": "Wool Runner Jacket",
                "url": "https://shop.example/wool-runner",
                "store": "Shop",
                "price": "98",
                "imageUrl": "https://images.example/wool-runner.jpg",
                "message": "Listed as recycled wool.",
            }
        ],
    )

    assert all(action["type"] != "compare_alternatives" for action in hidden["suggestedActions"])
    assert any(action["type"] == "compare_alternatives" for action in shown["suggestedActions"])
    assert any(action["type"] == "save_product" for action in shown["suggestedActions"])


def test_the_open_page_can_name_a_material_without_inventing_a_footprint():
    report = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier={"name": "Alpine Jacket", "seller": {}, "reviews": [], "documents": [], "specs": []},
        outside={"reviews": [], "policies": [], "environment": []},
        notes=[],
        products=[],
        page_text="The Alpine Jacket shell is polyester. No carbon figure is printed here.",
    )

    sustainability = next(block for block in report["blocks"] if block["type"] == "sustainability_report")
    assert any(finding["value"] == "polyester" and finding["status"] == "manufacturer_claim" for finding in sustainability["findings"])
    assert "kg" not in _blob(report)


def test_the_agent_cannot_add_a_carbon_number_the_page_does_not_state():
    grounded = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside=OUTSIDE_MATERIALS,
        notes=[],
        products=[],
    )

    def complete(prompt: str) -> str:
        assert "Alpine Jacket" in prompt
        assert "recycled wool" in prompt
        return '{"verdict": "This jacket has a footprint of 99 kg CO2e.", "why": "Calculated from the wool."}'

    report = look_at_page(grounded, "The Alpine Jacket is recycled wool.", complete=complete)

    assert "99" not in _blob(report)
    assert report["summary"] == grounded["summary"]


def test_the_agent_can_phrase_a_verdict_from_the_page():
    grounded = build_report(
        name="Alpine Jacket",
        url="https://shop.example/products/alpine-jacket",
        dossier=ALPINE,
        outside=OUTSIDE_MATERIALS,
        notes=[],
        products=[],
    )

    def complete(prompt: str) -> str:
        assert "recycled wool" in prompt
        return '{"verdict": "The page lists recycled wool, and product-level emissions are unverified.", "why": "The material is named on the page."}'

    report = look_at_page(grounded, "Material: recycled wool. Sold by Northwind Outfitters.", complete=complete)

    assert report["summary"].startswith("The page lists recycled wool")
    assert "kg" not in _blob(report)


def test_page_notes_and_ask_keep_their_answers_and_add_a_report(monkeypatch):
    monkeypatch.setattr(
        "backend.app.main.page_report",
        lambda *args, **kwargs: {
            "notes": [{"kind": "concern", "title": "Returns", "message": "Returns within the first week."}],
            "visits": [],
            "dossier": ALPINE,
            "outside": OUTSIDE_MATERIALS,
            "brief": "Sold by Northwind Outfitters.",
            "active": True,
        },
    )
    monkeypatch.setattr("backend.app.main.record", lambda *args, **kwargs: None)
    notes = page_notes(
        PageNotesRequest(url="https://shop.example/products/alpine-jacket", product_page=True, page_text="Alpine Jacket")
    )
    assert notes["brief"] == "Sold by Northwind Outfitters."
    assert notes["report"]["demo"] is False
    assert any(block["type"] == "missing_evidence" for block in notes["report"]["blocks"])

    monkeypatch.setattr("backend.app.main.answer_question", lambda *args, **kwargs: "The page lists recycled wool.")
    monkeypatch.setattr("backend.app.main.offer_alternatives", lambda *args, **kwargs: {"products": [], "pageScore": 50})
    reply = ask(
        AskRequest(
            question="Is this product environmentally friendly?",
            url="https://shop.example/products/alpine-jacket",
            title="Alpine Jacket",
            dossier=ALPINE,
            product_page=True,
        )
    )
    assert reply["answer"] == "The page lists recycled wool."
    assert reply["products"] == []
    assert reply["report"]["demo"] is False
