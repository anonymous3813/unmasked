"""Seller, reviews, documents, and specs retrieved for one product."""

import re

_SELLER_PATTERNS = (
    re.compile(r"\bsold by\s+([^.\n]{2,80})", re.IGNORECASE),
    re.compile(r"\bships from\s+([^.\n]{2,80})", re.IGNORECASE),
    re.compile(r"\bseller:\s*([^.\n]{2,80})", re.IGNORECASE),
    re.compile(r"\bbrand:\s*([^.\n]{2,80})", re.IGNORECASE),
)
_REVIEW = re.compile(
    r"\b(?:out of 5|stars?|verified purchase|customers say|reviewers?)\b",
    re.IGNORECASE,
)
_SPEC = re.compile(
    r"^(material|fabric|weight|dimensions|size|color|colour|made in|capacity|battery|model)\s*[:\-]\s*(.{1,80})$",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_STOP = {
    "with",
    "from",
    "this",
    "that",
    "pack",
    "size",
    "new",
    "the",
    "and",
    "for",
}


def product_brief(name: str, dossier: dict | None = None, notes: list | None = None) -> str:
    """The Photon text: seller, reviews, returns, and damage, only from what was retrieved."""
    dossier = dossier or {}
    seller = str((dossier.get("seller") or {}).get("detail") or "").strip() or "The seller was not named."
    reviews = dossier.get("reviews") or []
    review = str(reviews[0].get("quote") or "").strip() if reviews else ""
    review = review or "No reviews were retrieved."
    returns = _policy(notes or [], "return") or "No return policy was retrieved."
    damage = _policy(notes or [], "damage") or "No damage policy was retrieved."
    text = f"{name or 'This product'}. {seller} Reviews: {review} Returns: {returns} Damage: {damage}"
    return _clip(" ".join(text.split()), 900)


def _policy(notes: list, word: str) -> str:
    for note in notes:
        title = str(note.get("title") or "")
        message = str(note.get("message") or "")
        if word in f"{title} {message}".lower() and message.strip():
            return message.strip()
    return ""


def outside_evidence(name: str, search=None) -> dict:
    """Reviews, policies, and carbon notes from other sites that name this product."""
    from backend.app.services.catalog.identity import mentions_product, search_label

    found = {"reviews": [], "policies": [], "environment": []}
    product = " ".join(str(name or "").split())[:120]
    label = search_label(product)
    if len(label) < 4:
        return found
    search = search or _default_search
    queries = (
        ("review", f"{label} review"),
        ("policy", f"{label} return policy warranty"),
        ("environment", f"{label} carbon footprint materials CO2e"),
    )
    hits = []
    for kind, query in queries:
        try:
            batch = search(query) or []
        except (RuntimeError, OSError, TypeError):
            batch = []
        for hit in batch:
            if isinstance(hit, dict):
                hits.append((kind, hit))
    seen: set[str] = set()
    for kind, hit in hits:
        title = str(hit.get("title") or "")
        url = str(hit.get("url") or "").strip()
        content = " ".join(str(hit.get("content") or "").split())
        blob = f"{title} {content}"
        if not url or url in seen or not (mentions_product(label, blob) or mentions_product(product, blob)):
            continue
        seen.add(url)
        source = _clip(title, 80) or _title_from_url(url)
        if kind == "review" and len(found["reviews"]) < 4 and (_REVIEW.search(blob) or "review" in blob.lower()):
            found["reviews"].append({"quote": _clip(content or title, 280), "source": source, "url": url})
        elif kind == "policy" and len(found["policies"]) < 3 and re.search(r"return|refund|warrant", blob, re.I):
            found["policies"].append({"title": source, "text": _clip(content or title, 280), "url": url})
        elif kind == "environment" and len(found["environment"]) < 3 and re.search(
            r"carbon|co2|recycl|polyester|plastic|wool|organic|emission|footprint", blob, re.I
        ):
            found["environment"].append({"text": _clip(content or title, 280), "source": source, "url": url})
    return found


def _mentions(name: str, text: str) -> bool:
    words = [word for word in re.findall(r"[a-z0-9]+", name.lower()) if (len(word) > 3 or word == "tv") and word not in _STOP]
    if not words:
        return False
    haystack = text.lower()
    needed = words[:4]
    return sum(1 for word in needed if word in haystack) >= min(2, len(needed))


def _default_search(query: str) -> list[dict]:
    from backend.app.integrations.tavily_client import TavilyClient

    return TavilyClient().search(query, max_results=4)


def empty_dossier(name: str = "") -> dict:
    """A product record with nothing retrieved yet."""
    return {"name": name, "seller": {}, "reviews": [], "documents": [], "specs": []}


def build_dossier(
    url: str,
    page_text: str = "",
    record: dict | None = None,
    documents: list | None = None,
    search=None,
    name: str = "",
) -> dict:
    """Collect what the page, its documents, and a product search actually say.

    Search hits are kept only when they mention this product. Missing sections
    stay empty instead of being filled in.
    """
    record = record or {}
    product_name = _clip(str(record.get("name") or name or ""), 160)
    dossier = empty_dossier(product_name)
    dossier["seller"] = _seller(page_text, record)
    dossier["reviews"] = _reviews(page_text, record)
    dossier["documents"] = _documents(record, documents)
    dossier["specs"] = _specs(page_text, record)
    if search is not None and product_name:
        _add_search(dossier, product_name, search)
    return dossier


def _seller(page_text: str, record: dict) -> dict:
    named = _clip(str(record.get("seller") or ""), 80)
    if named:
        return {"name": named, "detail": f"Sold by {named}", "source": "This page"}
    for pattern in _SELLER_PATTERNS:
        match = pattern.search(page_text or "")
        if match is None:
            continue
        name = _clean_name(match.group(1))
        if name:
            return {"name": name, "detail": match.group(0).strip(), "source": "This page"}
    return {}


def _reviews(page_text: str, record: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in record.get("reviews") or []:
        if not isinstance(item, dict):
            continue
        quote = _clip(str(item.get("quote") or ""), 280)
        if not quote or quote.lower() in seen:
            continue
        seen.add(quote.lower())
        rows.append(
            {
                "quote": quote,
                "source": _clip(str(item.get("source") or "This page"), 80) or "This page",
                "url": str(item.get("url") or ""),
            }
        )
    for sentence in _SENTENCE.split(page_text or ""):
        clean = " ".join(sentence.split())
        if len(clean) < 40 or len(clean) > 280 or not _REVIEW.search(clean):
            continue
        if clean.lower() in seen:
            continue
        seen.add(clean.lower())
        rows.append({"quote": clean, "source": "This page", "url": ""})
        if len(rows) >= 6:
            break
    return rows[:6]


def _documents(record: dict, documents: list | None) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in list(record.get("documents") or []) + list(documents or []):
        if isinstance(item, dict):
            url = str(item.get("url") or "")
            title = str(item.get("title") or "")
            text = str(item.get("excerpt") or item.get("extracted_text") or "")
            kind = str(item.get("kind") or "document")
        else:
            url = str(getattr(item, "url", "") or "")
            title = ""
            text = str(getattr(item, "extracted_text", "") or "")
            kind = "policy"
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "title": _clip(title, 120) or _title_from_url(url),
                "url": url,
                "excerpt": _excerpt(text),
                "kind": kind or "document",
            }
        )
        if len(rows) >= 8:
            break
    return rows


def _specs(page_text: str, record: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in record.get("specs") or []:
        if not isinstance(item, dict):
            continue
        label = _clip(str(item.get("label") or ""), 40)
        value = _clip(str(item.get("value") or ""), 80)
        if not label or not value or label.lower() in seen:
            continue
        seen.add(label.lower())
        rows.append({"label": label, "value": value})
    for line in (page_text or "").splitlines():
        match = _SPEC.match(" ".join(line.split()))
        if match is None:
            continue
        label = match.group(1).strip().capitalize()
        value = _clip(match.group(2), 80)
        if not value or label.lower() in seen:
            continue
        seen.add(label.lower())
        rows.append({"label": label, "value": value})
        if len(rows) >= 8:
            break
    return rows[:8]


def _add_search(dossier: dict, name: str, search) -> None:
    query = f'"{name}" reviews seller specifications warranty manual'
    try:
        hits = search(query) or []
    except RuntimeError:
        return
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "")
        url = str(hit.get("url") or "")
        content = " ".join(str(hit.get("content") or "").split())
        blob = f"{title} {content}"
        seller_name = str((dossier.get("seller") or {}).get("name") or "")
        if not url or not _about_product(name, blob, seller_name):
            continue
        lowered = blob.lower()
        if _REVIEW.search(blob) and len(dossier["reviews"]) < 6:
            dossier["reviews"].append(
                {"quote": _clip(content or title, 280), "source": _clip(title, 80) or url, "url": url}
            )
            continue
        if any(word in lowered for word in ("sold by", "seller", "brand")) and not dossier["seller"]:
            dossier["seller"] = {
                "name": "",
                "detail": _clip(content or title, 180),
                "source": url,
            }
        if len(dossier["documents"]) < 8 and any(
            word in lowered for word in ("manual", "specification", "warranty", "datasheet", ".pdf")
        ):
            dossier["documents"].append(
                {
                    "title": _clip(title, 120) or _title_from_url(url),
                    "url": url,
                    "excerpt": _clip(content, 180),
                    "kind": "document",
                }
            )


def _about_product(name: str, text: str, seller: str = "") -> bool:
    phrase = " ".join(name.lower().split())
    haystack = text.lower()
    if len(phrase) < 4 or phrase not in haystack:
        return False
    seller_tokens = [word for word in re.findall(r"[a-z0-9]{5,}", seller.lower()) if word not in _STOP]
    if seller_tokens and not any(token in haystack for token in seller_tokens):
        return False
    return True


def _excerpt(text: str) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    sentence = _SENTENCE.split(clean)[0]
    if 40 <= len(sentence) <= 240:
        return sentence
    return _clip(clean, 180)


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
    return slug or url


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    name = re.split(r"\s{2,}|\||\s+-\s+", name)[0].strip(" -,:;")
    return _clip(name, 80)


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
