"""The public agent registry and the extension download."""

import io
import zipfile
from pathlib import Path

from backend.app.main import download_extension, read_registry
from backend.app.services.registry.log import record, reset, snapshot


def test_page_check_appears_in_the_registry():
    reset()
    record("page", "example.com", "Return limit", "https://example.com/jacket")

    page = [entry for entry in snapshot()["entries"] if entry["kind"] == "page"]

    assert page[0]["title"] == "example.com"
    assert page[0]["detail"] == "Return limit"
    assert snapshot()["counts"]["page"] == 1


def test_agents_vote_in_two_rounds_before_a_line_is_added():
    reset()
    entry = record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")

    assert entry["ballot"]["admitted"] is True
    assert [round_["name"] for round_ in entry["ballot"]["rounds"]] == ["First vote", "Second vote"]
    assert entry["ballot"]["rounds"][0]["agents"][0]["story"].startswith("Ada spoke first.")
    assert snapshot()["counts"]["page"] == 1


def test_fern_and_gale_join_the_table_and_four_votes_are_required():
    from backend.app.services.registry.vote import _AGENTS, _commits

    reset()
    entry = record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")
    names = [agent["name"] for agent in entry["ballot"]["rounds"][0]["agents"]]

    assert names == ["Ada", "Basil", "Cora", "Dex", "Esther", "Fern", "Gale"]
    assert all(len(round_["agents"]) == 7 for round_ in entry["ballot"]["rounds"])
    assert entry["ballot"]["quorum"] == 4
    assert entry["ballot"]["yes"] >= 4
    assert entry["ballot"]["admitted"] is True
    minority = [{"name": name, "vote": "yes" if index < 3 else "no", "hard": False} for index, (name, _role) in enumerate(_AGENTS)]
    majority = [{"name": name, "vote": "yes" if index < 4 else "no", "hard": False} for index, (name, _role) in enumerate(_AGENTS)]
    blocked = [{"name": name, "vote": "no" if index == 0 else "yes", "hard": index == 0} for index, (name, _role) in enumerate(_AGENTS)]
    assert _commits(minority) is False
    assert _commits(majority) is True
    assert _commits(blocked) is False


def test_a_line_with_no_time_is_kept_out_of_the_registry():
    from backend.app.services.registry.vote import deliberate

    ballot = deliberate(
        {
            "id": "R0009",
            "kind": "page",
            "title": "example.com",
            "detail": "Return limit on this jacket",
            "url": "https://example.com/jacket",
        },
        None,
    )
    fern = next(agent for agent in ballot["rounds"][1]["agents"] if agent["name"] == "Fern")

    assert fern["vote"] == "no"
    assert ballot["admitted"] is False


def test_a_duplicate_line_stays_out_of_the_registry():
    reset()
    record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")
    again = record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")

    assert again["ballot"]["admitted"] is False
    assert snapshot()["counts"]["page"] == 1


def test_privacy_and_terms_cover_the_text_program():
    from backend.app.main import privacy_policy, terms

    privacy = privacy_policy().body.decode()
    rules = terms().body.decode()

    assert "mobile number" in privacy.lower()
    assert "not sold" in privacy.lower()
    assert "STOP" in rules
    assert "HELP" in rules
    assert "Message and data rates may apply." in rules


def test_site_offers_the_extension_and_the_registry():
    page = (Path(__file__).resolve().parents[3] / "web" / "src" / "App.jsx").read_text()
    archive = download_extension()
    registry = read_registry()

    assert "Download the extension" in page
    assert "Agent registry" in page
    archive_file = zipfile.ZipFile(io.BytesIO(archive.body))
    names = archive_file.namelist()
    assert "unmasked/manifest.json" in names
    manifest = archive_file.read("unmasked/manifest.json").decode()
    script = archive_file.read("unmasked/src/background.js").decode()
    assert "stay private" in manifest
    assert "https://unmasked.fastapicloud.dev" in script
    assert "entries" in registry


def test_a_shopper_order_stays_off_the_public_registry():
    from backend.app.services.shop.cart import purchase

    reset()
    purchase(
        [{"name": "Private Jacket", "url": "https://shop.example/private", "price": "$10"}],
        user_id="ada-private",
    )
    blob = " ".join(f"{entry['title']} {entry['detail']}" for entry in snapshot()["entries"])

    assert "Private Jacket" not in blob
