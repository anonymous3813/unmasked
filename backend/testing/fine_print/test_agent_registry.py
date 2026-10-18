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


def test_a_duplicate_line_stays_out_of_the_registry():
    reset()
    record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")
    again = record("page", "example.com", "Return limit on this jacket", "https://example.com/jacket")

    assert again["ballot"]["admitted"] is False
    assert snapshot()["counts"]["page"] == 1


def test_site_offers_the_extension_and_the_registry():
    page = (Path(__file__).resolve().parents[3] / "registry-site" / "index.html").read_text()
    archive = download_extension()
    registry = read_registry()

    assert "Download the extension" in page
    assert "Agent registry" in page
    names = zipfile.ZipFile(io.BytesIO(archive.body)).namelist()
    assert "unmasked/manifest.json" in names
    assert "entries" in registry
