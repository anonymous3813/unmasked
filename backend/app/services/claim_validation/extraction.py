"""Extraction of product claims made by the seller."""

import re
from pathlib import Path

from trafilatura import extract, fetch_url

from backend.app.models.claim_validation import ProductClaim

_CATEGORY_PRIORITY = ("certification", "absolute", "comparative", "quantitative")
_STRONG_CATEGORIES = {"certification", "absolute", "comparative"}
_LOGISTICS = re.compile(
    r"\b(?:ships?|shipping|delivery|arrives|returns?|refunds?)\b",
    re.IGNORECASE,
)


class ClaimExtractor:
    """Pull the claims a seller makes on a product page.

    Sentences are kept when they use the claim vocabulary: certifications,
    absolute promises, comparisons, and measured performance. Shipping and
    return sentences are left for fine-print handling.
    """

    def __init__(self, fetch=None, extract_html=None, keywords_path: Path | None = None) -> None:
        self._fetch = fetch or fetch_url
        self._extract_html = extract_html or _extract_with_trafilatura
        if keywords_path is None:
            keywords_path = Path(__file__).resolve().parents[3] / "claim_words.txt"
        self._keywords = _load_keywords(keywords_path)

    def extract(self, url: str) -> list[ProductClaim]:
        """Return seller claims from one product page."""
        html = self._fetch(url)
        if not html:
            raise RuntimeError(f"Failed to fetch URL: {url}")
        text = self._extract_html(html)
        if not text or not text.strip():
            raise RuntimeError(f"Failed to extract text from URL: {url}")

        product_name, sentences = _read_page(text)
        claims: list[ProductClaim] = []
        seen: set[str] = set()
        for sentence in sentences:
            category = _claim_category(sentence, self._keywords)
            if category is None:
                continue
            if _LOGISTICS.search(sentence) and category not in _STRONG_CATEGORIES:
                continue
            key = " ".join(sentence.lower().split())
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                ProductClaim(
                    claim_text=sentence,
                    product_name=product_name,
                    source_url=url,
                    category=category,
                )
            )
        return claims


def _extract_with_trafilatura(html: str) -> str:
    text = extract(html, output_format="markdown", with_metadata=True, include_tables=True)
    return text or ""


def _load_keywords(path: Path) -> dict[str, list[str]]:
    keywords: dict[str, list[str]] = {}
    category = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            category = stripped[1:-1].lower()
            keywords[category] = []
        elif category is not None:
            keywords[category].append(stripped)
    return keywords


def _read_page(text: str) -> tuple[str, list[str]]:
    product_name = "Unknown product"
    sentences: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#+\s+(.+)$", stripped)
        if heading:
            if product_name == "Unknown product":
                product_name = heading.group(1).strip()
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        parts = re.split(r"(?<=[.!?])\s+", stripped)
        sentences.extend(part.strip() for part in parts if part.strip())
    return product_name, sentences


def _claim_category(sentence: str, keywords: dict[str, list[str]]) -> str | None:
    matched = [
        category
        for category in _CATEGORY_PRIORITY
        if any(_contains_term(sentence, term) for term in keywords.get(category, []))
    ]
    if not matched:
        return None
    category = matched[0]
    if category == "quantitative" and not re.search(r"\d", sentence):
        return None
    return category


def _contains_term(sentence: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", sentence, re.IGNORECASE) is not None
