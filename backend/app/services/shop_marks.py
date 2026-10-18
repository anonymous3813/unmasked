"""Notices to draw on the product page the shopper is viewing."""

import os
import re
from html import unescape
from urllib.parse import urlparse

from backend.app.integrations.gemini_client import _load_local_env
from backend.app.integrations.tavily_client import TavilyClient
from backend.app.models.fine_print import FinePrintExtraction
from backend.app.services.claim_validation.analysis import ClaimAnalysisService
from backend.app.services.claim_validation.extraction import ClaimExtractor
from backend.app.services.fine_print.analysis import FinePrintAnalyzer
from backend.app.services.fine_print.extraction import FinePrintExtractor

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_RETURN = re.compile(r"\b(?:return|refund|exchange)\b", re.IGNORECASE)
_DAMAGE = re.compile(r"\b(?:damage|warranty)\b", re.IGNORECASE)
_TAX_INCLUDED = re.compile(r"tax included|including tax|includes tax", re.IGNORECASE)
_PRICE = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)")


_ALTERNATIVE_QUERIES = (
    "environmentally friendly alternatives",
    "best value alternatives",
    "durable alternatives",
)


def notes_for_url(url: str, listed_price: str | None = None) -> list[dict]:
    """Read one product page and return the marks to draw on it."""
    return page_report(url, listed_price)["notes"]


def page_report(url: str, listed_price: str | None = None) -> dict:
    """Return the on-page marks and the sites read while building them."""
    try:
        extraction = FinePrintExtractor().extract(url)
    except RuntimeError:
        return {"notes": [], "visits": []}
    analysis = None
    recommendations = []
    hits: list[tuple[str, dict]] = []
    if _gemini_ready():
        try:
            analysis = FinePrintAnalyzer().analyze(extraction)
        except RuntimeError:
            analysis = None
        recommendations = _recommendations(url, hits)
    return {
        "notes": notes_from_page(extraction, listed_price, analysis, recommendations),
        "visits": collect_visits([str(document.url) for document in extraction.documents], hits),
    }


def collect_visits(policy_urls: list[str], hits: list[tuple[str, dict]]) -> list[dict]:
    """List each policy page and review site once."""
    visits: list[dict] = []
    seen: set[str] = set()
    for url in policy_urls:
        _add_visit(visits, seen, url, _label(url), "Policy page")
    for query, hit in hits:
        url = str(hit.get("url") or "").strip()
        title = str(hit.get("title") or "").strip() or _label(url)
        _add_visit(visits, seen, url, title, _search_reason(query))
    return visits


def _recommendations(url: str, hits: list[tuple[str, dict]]) -> list:
    try:
        claims = ClaimExtractor().extract(url)
    except RuntimeError:
        return []
    if not claims:
        return []

    def search(query: str) -> list[dict]:
        found = TavilyClient().search(query)
        hits.extend((query, hit) for hit in found if isinstance(hit, dict))
        return found

    try:
        return ClaimAnalysisService(search=search).analyze(claims).recommendations
    except RuntimeError:
        product_name = claims[0].product_name
        logged = {query for query, _hit in hits}
        for phrase in _ALTERNATIVE_QUERIES:
            query = f'"{product_name}" {phrase} reviews'
            if query in logged:
                continue
            try:
                search(query)
            except RuntimeError:
                continue
        return []


def _add_visit(visits: list[dict], seen: set[str], url: str, title: str, reason: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    key = f"{parsed.scheme.lower()}://{host}{parsed.path.rstrip('/')}"
    if key in seen:
        return
    seen.add(key)
    visits.append({"title": title, "url": url, "site": host, "reason": reason})


def _label(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
    return slug or _add_visit_host(url)


def _add_visit_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _search_reason(query: str) -> str:
    lowered = query.lower()
    if "environmentally friendly alternatives" in lowered:
        return "Environmentally friendly alternatives"
    if "best value alternatives" in lowered:
        return "Best value alternatives"
    if "durable alternatives" in lowered:
        return "Durable alternatives"
    return "Reviews of the seller's claim"


def notes_from_page(
    extraction: FinePrintExtraction,
    listed_price: str | None = None,
    analysis=None,
    recommendations=None,
) -> list[dict]:
    """Turn an extraction into on-page marks."""
    notes: list[dict] = []
    price = _price_note(extraction, listed_price, analysis)
    if price is not None:
        notes.append(price)
    notes.extend(_concern_notes(extraction, analysis))
    for item in recommendations or []:
        notes.append(
            {
                "kind": "recommendation",
                "aspect": item.aspect.value,
                "title": item.product_name,
                "productName": item.product_name,
                "message": item.reason,
                "productUrl": str(item.product_url),
                "imageUrl": str(item.image_url),
                "price": item.price,
            }
        )
    return notes


def _price_note(extraction, listed_price, analysis) -> dict | None:
    if analysis is not None and analysis.price is not None:
        price = analysis.price
        return {
            "kind": "price",
            "title": "Price with tax",
            "message": price.explanation,
            "listedPrice": price.listed_price,
            "priceWithTax": price.price_with_tax,
        }
    amount = _amount(listed_price) or _amount_in(extraction.page_text)
    if amount is None or _TAX_INCLUDED.search(extraction.page_text):
        return None
    return {
        "kind": "price",
        "title": "Price with tax",
        "message": (
            f"The page shows USD {amount}. "
            "That price does not include tax, and no tax rate is stated, "
            "so the checkout total will be higher."
        ),
        "listedPrice": amount,
    }


def _concern_notes(extraction, analysis) -> list[dict]:
    if analysis is not None and analysis.findings:
        return [
            {
                "kind": "concern",
                "title": _title(finding.category.value),
                "message": f"{finding.explanation} {finding.evidence_quotation}",
            }
            for finding in analysis.findings
        ]
    notes = []
    page = _normalize(extraction.page_text)
    for document in extraction.documents:
        if "privacy" in str(document.url):
            continue
        sentence = _hidden_sentence(document.extracted_text, page)
        if sentence is None:
            continue
        notes.append(
            {
                "kind": "concern",
                "title": "Damage policy" if _DAMAGE.search(sentence) and not _RETURN.search(sentence) else "Return limit",
                "message": sentence,
            }
        )
    return notes


def _hidden_sentence(text: str, page: str) -> str | None:
    candidates = []
    for sentence in _SENTENCE.split(text):
        cleaned = " ".join(sentence.split())
        if len(cleaned) < 36 or len(cleaned) > 320 or "|" in cleaned:
            continue
        if cleaned.startswith("---") or "hostname:" in cleaned or "fingerprint:" in cleaned:
            continue
        if not _RETURN.search(cleaned) and not _DAMAGE.search(cleaned):
            continue
        if _normalize(cleaned) in page:
            continue
        candidates.append(cleaned)
    if not candidates:
        return None
    return sorted(candidates, key=_sentence_rank)[0]


def _sentence_rank(sentence: str) -> tuple[int, int]:
    lowered = sentence.lower()
    score = 0
    if "unworn" in lowered or "tag" in lowered:
        score += 3
    if "day" in lowered:
        score += 2
    if "fee" in lowered or "charge" in lowered or "final sale" in lowered:
        score += 2
    return (-score, -len(sentence))


def _title(category: str) -> str:
    return {
        "return_restriction": "Return limit",
        "restocking_fee": "Restocking fee",
        "cancellation_trap": "Cancellation terms",
        "warranty_exclusion": "Warranty exclusion",
        "damage_policy": "Damage policy",
    }.get(category, "Product concern")


def _amount(value: str | None) -> str | None:
    if not value:
        return None
    match = _PRICE.search(value) or re.search(r"(\d+(?:\.\d{2})?)", value)
    if match is None:
        return None
    number = match.group(1).replace(",", "")
    if "." not in number:
        number = f"{number}.00"
    return number


def _amount_in(text: str) -> str | None:
    match = _PRICE.search(text)
    if match is None:
        return None
    return _amount(match.group(0))


def _normalize(text: str) -> str:
    return unescape(" ".join(text.lower().split()))


def _gemini_ready() -> bool:
    _load_local_env()
    return bool(os.environ.get("GEMINI_API_KEY"))
