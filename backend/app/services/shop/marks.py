"""Notices to draw on the product page the shopper is viewing."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import urlparse

from backend.app.integrations.gemini_client import _load_local_env
from backend.app.integrations.tavily_client import TavilyClient
from backend.app.models.fine_print import FinePrintExtraction
from backend.app.services.claim_validation.analysis import ClaimAnalysisService, recommend_alternatives
from backend.app.services.shop.products import find_products
from backend.app.services.claim_validation.extraction import ClaimExtractor
from backend.app.services.fine_print.analysis import FinePrintAnalyzer
from backend.app.services.fine_print.extraction import FinePrintExtractor
from backend.app.services.catalog.dossier import build_dossier, empty_dossier, outside_evidence, product_brief
from backend.app.services.catalog.page import accepts_page
from backend.app.services.shop.tax import tax_note

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_RETURN = re.compile(r"\b(?:returns?|refunds?|exchanges?|buyer protection)\b", re.IGNORECASE)
_DAMAGE = re.compile(r"\b(?:damag\w*|warranty)\b", re.IGNORECASE)
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


def page_report(
    url: str,
    listed_price: str | None = None,
    postal_code: str | None = None,
    page_text: str = "",
    record: dict | None = None,
    product_page: bool = False,
) -> dict:
    """Return the on-page marks and the sites read while building them."""
    if not accepts_page(url, product_page):
        return {"notes": [], "visits": [], "dossier": empty_dossier(), "brief": "", "active": False}
    extraction = None
    try:
        extraction = FinePrintExtractor().extract(url)
    except RuntimeError:
        extraction = None
    analysis = None
    recommendations = []
    hits: list[tuple[str, dict]] = []
    notes: list[dict] = []
    visits: list[dict] = []
    if extraction is not None:
        if _gemini_ready():
            try:
                analysis = FinePrintAnalyzer().analyze(extraction)
            except RuntimeError:
                analysis = None
            recommendations = _recommendations(url, hits)
        notes = notes_from_page(
            extraction, listed_price, analysis, recommendations, postal_code
        )
        visits = collect_visits([str(document.url) for document in extraction.documents], hits)
    for note in notes_from_browser(page_text, listed_price, postal_code):
        if any(existing.get("message") == note.get("message") for existing in notes):
            continue
        if note["kind"] == "price" and any(existing.get("kind") == "price" for existing in notes):
            continue
        notes.append(note)
    product_name = _named_product(record, page_text)
    search = _product_search(hits) if product_name and _tavily_ready() else None
    dossier = build_dossier(
        url,
        page_text or (extraction.page_text if extraction is not None else ""),
        record,
        list(extraction.documents) if extraction is not None else [],
        search,
        product_name,
    )
    description = " ".join(str((record or {}).get("description") or "").split())[:800]
    notes = _add_review_alternatives(notes, product_name, hits, url, description)
    seller_name = str((dossier.get("seller") or {}).get("name") or (record or {}).get("brand") or "")
    outside = outside_evidence(product_name, seller=seller_name) if product_name and _tavily_ready() else {
        "reviews": [],
        "policies": [],
        "environment": [],
    }
    seen_visits = {str(visit.get("url") or "") for visit in visits}
    for row in [*outside["reviews"], *outside["policies"], *outside["environment"]]:
        _add_visit(visits, seen_visits, str(row.get("url") or ""), str(row.get("source") or row.get("title") or ""), "Outside source")
    return {
        "notes": notes,
        "visits": visits,
        "dossier": dossier,
        "outside": outside,
        "brief": product_brief(product_name or dossier.get("name") or "", dossier, notes),
        "footprint": _footprint(product_name, page_text, dossier, url),
        "active": True,
    }


def _add_review_alternatives(
    notes: list[dict],
    name: str,
    hits: list[tuple[str, dict]],
    url: str = "",
    description: str = "",
) -> list[dict]:
    """Add greener and better-value products named by reviews, then priced listings."""
    if not name or not _tavily_ready():
        return notes
    kind = _product_type(name) or _agent_kind(name, description)
    if not kind:
        return notes
    aspects = {str(note.get("aspect") or "") for note in notes if note.get("kind") == "recommendation"}
    if {"environmental", "cost_value", "reviews"} <= aspects:
        return notes

    def search(query: str) -> list[dict]:
        try:
            found = TavilyClient().search(query, max_results=4)
        except RuntimeError:
            return []
        hits.extend((query, hit) for hit in found if isinstance(hit, dict))
        return found

    found = []
    if _gemini_ready():
        try:
            found = recommend_alternatives(name, search)
        except RuntimeError:
            found = []
    from backend.app.services.shop.products import _matches

    known = {str(note.get("productName") or "").lower() for note in notes}
    for item in found:
        if not _matches(kind, str(item.product_name or "").lower()):
            continue
        if item.product_name.lower() in known:
            continue
        known.add(item.product_name.lower())
        aspects.add(item.aspect.value)
        notes.append(
            {
                "kind": "recommendation",
                "aspect": item.aspect.value,
                "title": item.product_name,
                "productName": item.product_name,
                "message": item.reason,
                "quotation": item.evidence_quotation,
                "productUrl": str(item.product_url),
                "imageUrl": str(item.image_url or ""),
                "price": item.price,
                "environmentScore": environment_score(f"{item.product_name} {item.evidence_quotation} {item.reason}"),
            }
        )
    notes.extend(_priced_listing_notes(name, url, search, known, aspects, kind))
    return notes


_LISTING_ASPECTS = (
    ("environmental", "eco friendly"),
    ("cost_value", "best value"),
    ("reviews", "best reviewed"),
    ("same", ""),
)
_GREEN_WORDS = (
    "recycled",
    "organic",
    "sustainable",
    "renewable",
    "biodegradable",
    "repairable",
    "fair trade",
    "wool",
    "linen",
    "hemp",
    "cotton",
    "eco",
    "water saving",
    "water-saving",
    "low-flow",
    "low flow",
)
_HARM_WORDS = ("polyester", "nylon", "acrylic", "plastic", "vinyl", "polyurethane", "non-recyclable")
_ASPECT_LABELS = {
    "same": "Same kind",
    "environmental": "Greener",
    "cost_value": "Better value",
    "reviews": "Better reviewed",
    "durability": "More durable",
}


def environment_score(text: str) -> int:
    """Score materials language from 8 to 96. A page with neither kind of word stays at 50."""
    hay = (text or "").lower()
    score = 50
    for word in _GREEN_WORDS:
        if word in hay:
            score += 12
    for word in _HARM_WORDS:
        if word in hay:
            score -= 12
    return max(8, min(96, score))


def offer_alternatives(
    name: str,
    url: str = "",
    page_text: str = "",
    listed_price: str | None = None,
    user_id: str = "shopper",
) -> dict:
    """Return priced alternatives of the same kind. An unknown kind is not filled with unrelated listings."""
    del listed_price
    page_score = environment_score(page_text)
    if not name or not _tavily_ready():
        return {"products": [], "pageScore": page_score, "coverage": "Other stores were not searched because the product name was missing."}
    description = " ".join(page_text.split())[:800]
    from backend.app.services.catalog.identity import search_label

    kind = _product_type(name) or _agent_kind(name, description) or search_label(name) or " ".join(name.split()[:4])
    if not str(kind).strip():
        return {"products": [], "pageScore": page_score, "coverage": "The product type was not clear enough to search other brands."}

    def search(query: str) -> list[dict]:
        try:
            return TavilyClient().search(query, max_results=4, include_images=True)
        except (RuntimeError, OSError, TimeoutError):
            return []

    notes = _priced_listing_notes(name, url, search, set(), set(), kind)
    from backend.app.services.shop.products import loose_products

    if len(notes) < 4:
        notes = _merge_cards(notes, find_products(kind, current_url=url, search=search), name, url)
    if len(notes) < 4:
        notes = _merge_cards(notes, loose_products(kind, url, search), name, url)
    from backend.app.services.shop.taste import load_taste, personalize

    taste = load_taste(user_id)
    scored = _with_scores(_carousel_products(notes), search)
    ranked = personalize(scored, taste)[:8] or scored[:8]
    pictured = _with_images(ranked, search)
    products = pictured or [item for item in ranked if str(item.get("url") or "").startswith("http")]
    if pictured:
        coverage = ""
    elif products:
        coverage = "Listings were retrieved from other stores. A product photo was not on every result."
    else:
        coverage = f"No other-store listing was retrieved for {kind}. The search checked the major retailers for this kind of product."
    return {"products": products, "pageScore": page_score, "taste": taste, "coverage": coverage}


_STARS = re.compile(r"(\d(?:\.\d)?)\s*(?:/|out of)\s*5|\b(\d(?:\.\d)?)\s*stars?\b", re.IGNORECASE)
_KILOS = re.compile(r"(\d{1,4})\s*(?:–|-|to)\s*(\d{1,4})\s*kg", re.IGNORECASE)


def _with_scores(products: list[dict], search) -> list[dict]:
    """Look up a review score and a carbon range for each similar product."""

    def one(product: dict) -> dict:
        label = " ".join(str(product.get("name") or "").split())[:80]
        if not label:
            return product
        reviews = _safe_hits(search, f"{label} review rating out of 5")
        carbon = _safe_hits(search, f"{label} carbon footprint kg CO2e")
        extra = {}
        score = _review_score(reviews)
        span = _carbon_span(carbon)
        if score:
            extra["reviewScore"] = score
        else:
            extra["reviewNote"] = "No review score was published for this listing."
        if span:
            extra["footprintLow"], extra["footprintHigh"] = span
            extra["footprintNote"] = "Published range."
        else:
            from backend.app.services.catalog.footprint import estimate_footprint

            estimate = estimate_footprint(label, str(product.get("message") or product.get("quotation") or ""))
            if estimate.get("low") and estimate.get("high"):
                extra["footprintLow"] = estimate["low"]
                extra["footprintHigh"] = estimate["high"]
                extra["footprintNote"] = "Estimate for this kind of product, not a measurement of this listing."
            else:
                extra["footprintNote"] = "No carbon range was published for this listing."
        if not str(product.get("price") or "").strip():
            extra["priceNote"] = "Price was not on the listing."
        return {**product, **extra}

    if not products:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(products))) as pool:
        return list(pool.map(one, products))


def _with_images(products: list[dict], search) -> list[dict]:
    """Keep a similar product once it has a real photo. A letter in place of a picture is not shown."""
    ready = []
    for product in products:
        image = str(product.get("imageUrl") or "").strip()
        if not image.startswith("http"):
            label = " ".join(str(product.get("name") or "").split())[:80]
            store = str(product.get("store") or "").split(" · ")[-1]
            for hit in _safe_hits(search, f"{label} {store} product photo".strip()):
                image = _photo(hit)
                if image:
                    break
        if not image.startswith("http"):
            continue
        ready.append({**product, "imageUrl": image})
    return ready


def _photo(hit: dict) -> str:
    image = str(hit.get("image") or hit.get("imageUrl") or "").strip()
    if image.startswith("http"):
        return image
    blob = f"{hit.get('raw_content') or ''} {hit.get('content') or ''}"
    match = re.search(r"https://[^ \]'\"<>]+\.(?:jpg|jpeg|png|webp)", blob, re.IGNORECASE)
    return match.group(0) if match else ""


def _safe_hits(search, query: str) -> list[dict]:
    try:
        found = search(query) or []
    except (RuntimeError, OSError, TypeError):
        return []
    return [hit for hit in found if isinstance(hit, dict)]


def _review_score(hits: list[dict]) -> float | None:
    scores = []
    for hit in hits:
        blob = f"{hit.get('title') or ''} {hit.get('content') or ''}"
        for match in _STARS.finditer(blob):
            value = float(match.group(1) or match.group(2))
            if 1 <= value <= 5:
                scores.append(value)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _carbon_span(hits: list[dict]) -> tuple[int, int] | None:
    for hit in hits:
        blob = f"{hit.get('title') or ''} {hit.get('content') or ''}"
        match = _KILOS.search(blob)
        if match is None:
            continue
        low, high = int(match.group(1)), int(match.group(2))
        if high > low and high <= 2000:
            return low, high
    return None


def _merge_cards(notes: list[dict], cards: list[dict], page_name: str = "", page_url: str = "") -> list[dict]:
    """Add store listings that are not already on the list and are not this same page."""
    known = {str(note.get("productName") or note.get("title") or "").lower() for note in notes}
    urls = {str(note.get("productUrl") or "") for note in notes}
    merged = list(notes)
    for card in cards:
        product_name = str(card.get("name") or "").strip()
        product_url = str(card.get("url") or "").strip()
        if not product_name or not product_url.startswith("http") or product_name.lower() in known or product_url in urls:
            continue
        if _same_listing(page_name, page_url, product_name, product_url):
            continue
        known.add(product_name.lower())
        urls.add(product_url)
        price = str(card.get("price") or "").strip()
        store = str(card.get("store") or "").strip()
        snippet = str(card.get("message") or "").strip()
        merged.append(
            {
                "kind": "recommendation",
                "aspect": "same",
                "title": product_name,
                "productName": product_name,
                "store": store,
                "message": snippet or (f"Listed at {store} for ${price}." if price else f"Listed at {store}."),
                "quotation": snippet,
                "productUrl": product_url,
                "imageUrl": str(card.get("imageUrl") or ""),
                "price": price,
                "environmentScore": environment_score(f"{product_name} {snippet}"),
            }
        )
    return merged


def _same_listing(page_name: str, page_url: str, product_name: str, product_url: str) -> bool:
    """The open page itself is not an alternative. A shorter title for a different listing still is."""
    left_url = str(page_url or "").split("?")[0].rstrip("/")
    right_url = str(product_url or "").split("?")[0].rstrip("/")
    if left_url and right_url and left_url == right_url:
        return True

    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    left, right = norm(page_name), norm(product_name)
    return bool(left and right and left == right)


def _priced_listing_notes(name: str, url: str, search, known: set, aspects: set, kind: str = "") -> list[dict]:
    kind = kind or _product_type(name)
    if not kind:
        return []

    def load(pair: tuple[str, str]) -> tuple[str, list]:
        aspect, prefix = pair
        try:
            cards = find_products(kind, current_url=url, search=search, query_prefix=prefix)
        except (RuntimeError, OSError, TypeError):
            cards = []
        return aspect, cards

    with ThreadPoolExecutor(max_workers=len(_LISTING_ASPECTS)) as pool:
        batches = list(pool.map(load, _LISTING_ASPECTS))
    added = []
    for aspect, cards in batches:
        if aspect in aspects:
            continue
        for card in cards:
            product_name = str(card.get("name") or "").strip()
            product_url = str(card.get("url") or "").strip()
            price = str(card.get("price") or "").strip()
            if not product_name or not product_url or product_name.lower() in known:
                continue
            if _same_listing(name, url, product_name, product_url):
                continue
            known.add(product_name.lower())
            snippet = str(card.get("message") or "").strip()
            store = str(card.get("store") or "").strip()
            added.append(
                {
                    "kind": "recommendation",
                    "aspect": aspect,
                    "title": product_name,
                    "productName": product_name,
                    "store": store,
                    "message": snippet or (f"Listed at {store} for ${price}." if price else f"Listed at {store}."),
                    "quotation": snippet,
                    "productUrl": product_url,
                    "imageUrl": str(card.get("imageUrl") or ""),
                    "price": price,
                    "environmentScore": environment_score(f"{product_name} {snippet}"),
                }
            )
            if sum(1 for note in added if note.get("aspect") == aspect) >= 3:
                break
        if any(note.get("aspect") == aspect for note in added):
            aspects.add(aspect)
    return added


def _carousel_products(notes: list[dict]) -> list[dict]:
    products = []
    for note in notes:
        label = _ASPECT_LABELS.get(str(note.get("aspect") or ""), "")
        store = " · ".join(part for part in (label, note.get("store")) if part) or "Review"
        image_url = str(note.get("imageUrl") or "").strip()
        if image_url and not image_url.startswith("http"):
            image_url = ""
        products.append(
            {
                "name": note.get("productName") or note.get("title") or "",
                "url": note.get("productUrl") or "",
                "store": store,
                "price": note.get("price") or "",
                "imageUrl": image_url if image_url.startswith("http") else "",
                "message": note.get("message") or "",
                "quotation": note.get("quotation") or "",
                "environmentScore": note.get("environmentScore"),
                "aspect": note.get("aspect") or "",
            }
        )
    return products


def _named_product(record: dict | None, page_text: str) -> str:
    """Use the visible heading, then ask OpenAI which structured-data name is on screen."""
    import os

    record = record or {}
    heading = str(record.get("heading") or "").strip()
    title = str(record.get("name") or "").strip()
    candidates = [str(item) for item in (record.get("candidates") or []) if str(item).strip()]
    complete = None
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from backend.app.integrations.openai_client import OpenAIClient

            complete = OpenAIClient().complete
        except RuntimeError:
            complete = None
    from backend.app.services.catalog.identity import identify_product

    picked = identify_product(heading, title, candidates, page_text, complete)
    return str(picked.get("name") or heading or title).strip()


def _product_type(name: str) -> str:
    """Return a store category named in the title. An unknown title is not guessed from its last words."""
    from backend.app.services.catalog.identity import known_kind

    return known_kind(name)


def _agent_kind(name: str, page_text: str) -> str:
    """Ask OpenAI for the category when the title does not name one. Tests stay on the title."""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    try:
        from backend.app.integrations.openai_client import OpenAIClient
        from backend.app.services.catalog.identity import accept_kind, kind_from_model

        guessed = kind_from_model(name, page_text, OpenAIClient().complete)
        return accept_kind(name, page_text, guessed)
    except RuntimeError:
        return ""


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
    except (RuntimeError, OSError, ValueError):
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
    postal_code: str | None = None,
) -> list[dict]:
    """Turn an extraction into on-page marks."""
    notes: list[dict] = []
    price = _price_note(extraction, listed_price, analysis, postal_code)
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
                "quotation": item.evidence_quotation,
                "productUrl": str(item.product_url),
                "imageUrl": str(item.image_url or ""),
                "price": item.price,
            }
        )
    return notes


def _price_note(extraction, listed_price, analysis, postal_code) -> dict | None:
    stated = None
    if analysis is not None and analysis.price is not None and analysis.price.price_with_tax:
        stated = analysis.price
    amount = _amount(stated.listed_price) if stated is not None else None
    if amount is None:
        amount = _amount(listed_price) or _amount_in(extraction.page_text)
    if amount is None or _TAX_INCLUDED.search(extraction.page_text):
        return None
    if postal_code:
        return tax_note(amount, postal_code)
    if stated is None:
        return None
    return {
        "kind": "price",
        "title": "Price with tax",
        "symbol": "+",
        "label": f"${stated.price_with_tax}",
        "message": stated.explanation,
        "listedPrice": stated.listed_price,
        "priceWithTax": stated.price_with_tax,
    }


def _short_label(sentence: str) -> str:
    lowered = sentence.lower()
    if "30 day" in lowered:
        extra = " · you pay shipping" if "shipping" in lowered and "responsible" in lowered else ""
        return f"30-day return{extra}"
    words = sentence.split()
    short = " ".join(words[:8])
    return short[:48].rstrip(".,")


def _symbol(title: str) -> str:
    return {
        "Return limit": "↩",
        "Restocking fee": "%",
        "Cancellation terms": "×",
        "Warranty exclusion": "✶",
        "Damage policy": "!",
    }.get(title, "•")


_CONSTRAINT = re.compile(
    r"\b(?:\d+\s*-?\s*(?:days?|hours?)|buyer protection|free returns?|refunds?|"
    r"not as described|damag\w*|defect\w*|warrant\w*|guarantee|money back|dispute|"
    r"first week|final sale|no returns?|restock|fee|unworn|"
    r"exclud\w*|not covered|you pay|buyer pays|original tags)\b",
    re.IGNORECASE,
)


def notes_from_browser(
    page_text: str,
    listed_price: str | None = None,
    postal_code: str | None = None,
) -> list[dict]:
    """Build marks from the product page the browser already loaded."""
    notes: list[dict] = []
    amount = _amount(listed_price) or _amount_in(page_text)
    if amount and postal_code and not _TAX_INCLUDED.search(page_text or ""):
        price = tax_note(amount, postal_code)
        if price is not None:
            notes.append(price)
    seen: set[str] = set()
    ranked = sorted(_policy_sentences(page_text), key=_sentence_rank)
    for sentence in ranked:
        title = _policy_title(sentence)
        if title in seen:
            continue
        seen.add(title)
        notes.append(
            {
                "kind": "concern",
                "title": title,
                "symbol": _symbol(title),
                "label": _short_label(sentence),
                "message": sentence,
            }
        )
        if len(seen) == 4:
            break
    return notes


def _policy_sentences(page_text: str) -> list[str]:
    found = []
    for sentence in _SENTENCE.split(page_text or ""):
        cleaned = " ".join(sentence.split())
        if len(cleaned) < 20 or len(cleaned) > 320 or "|" in cleaned:
            continue
        if not _CONSTRAINT.search(cleaned):
            continue
        if _policy_title(cleaned) == "":
            continue
        found.append(cleaned)
    return found


def _policy_title(sentence: str) -> str:
    if _RETURN.search(sentence):
        return "Return limit"
    if re.search(r"\brestock", sentence, re.IGNORECASE):
        return "Restocking fee"
    if re.search(r"\bcancel", sentence, re.IGNORECASE):
        return "Cancellation terms"
    if re.search(r"\bwarrant", sentence, re.IGNORECASE):
        return "Warranty exclusion"
    if _DAMAGE.search(sentence):
        return "Damage policy"
    return ""


def _concern_notes(extraction, analysis) -> list[dict]:
    if analysis is not None and analysis.findings:
        return [
            {
                "kind": "concern",
                "title": _title(finding.category.value),
                "symbol": _symbol(_title(finding.category.value)),
                "label": _short_label(finding.evidence_quotation),
                "message": finding.evidence_quotation,
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
                "symbol": "!" if _DAMAGE.search(sentence) and not _RETURN.search(sentence) else "↩",
                "label": _short_label(sentence),
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


def _footprint(name: str, page_text: str, dossier: dict, url: str) -> dict:
    """Read the material from the page, then look outside for a published range."""
    from backend.app.services.catalog.footprint import estimate_footprint, with_outside_sources

    estimate = estimate_footprint(name, page_text, (dossier or {}).get("specs") or [])
    if not _tavily_ready():
        return _with_coverage(estimate)

    def search(query: str) -> list[dict]:
        try:
            return TavilyClient().search(query, max_results=4)
        except RuntimeError:
            return []

    return _with_coverage(with_outside_sources(estimate, search, url))


def _with_coverage(estimate: dict) -> dict:
    if estimate.get("low") and estimate.get("high"):
        estimate["coverage"] = estimate.get("productHeadline") or estimate.get("headline") or ""
    else:
        material = str(estimate.get("material") or "").strip()
        named = f" The page names {material}." if material else ""
        estimate["coverage"] = "Product carbon footprint not independently verified." + named
    return estimate


def _tavily_ready() -> bool:
    _load_local_env()
    return bool(os.environ.get("TAVILY_API_KEY"))


def _product_search(hits: list[tuple[str, dict]]):
    """Search once for reviews, the seller, and documents about this product."""

    def search(query: str) -> list[dict]:
        try:
            found = TavilyClient().search(query, max_results=8)
        except (RuntimeError, OSError, TimeoutError):
            return []
        hits.extend((query, hit) for hit in found if isinstance(hit, dict))
        return found

    return search


def _gemini_ready() -> bool:
    _load_local_env()
    return bool(os.environ.get("GEMINI_API_KEY"))
