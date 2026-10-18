"""A footprint estimate from the material and the product type.

The page supplies the material and the kind. A published range for that pair
is read from other sites. The figure is not a measurement of the listing.
"""

import re
from urllib.parse import urlparse

from backend.app.services.catalog.identity import known_kind

_RANGE = re.compile(r"(\d{1,4})\s*(?:–|-|to)\s*(\d{1,4})\s*kg", re.IGNORECASE)

_MATERIALS = (
    "recycled wool",
    "organic cotton",
    "recycled polyester",
    "polyester",
    "nylon",
    "acrylic",
    "plastic",
    "wool",
    "cotton",
    "linen",
    "hemp",
    "leather",
    "aluminum",
    "steel",
)
# Typical finished-item ranges in kilograms of CO2e.
_RANGES = {
    ("jacket", "wool"): (20, 50),
    ("jacket", "polyester"): (10, 20),
    ("jacket", "nylon"): (12, 24),
    ("jacket", "cotton"): (8, 16),
    ("jacket", "leather"): (25, 60),
    ("coat", "wool"): (25, 60),
    ("shirt", "cotton"): (4, 9),
    ("shirt", "polyester"): (6, 12),
    ("hoodie", "cotton"): (8, 16),
    ("running shoe", "polyester"): (10, 18),
    ("running shoe", "nylon"): (12, 20),
    ("running shoe", "leather"): (15, 30),
    ("sneaker", "polyester"): (10, 18),
    ("handbag", "leather"): (12, 35),
    ("satchel", "leather"): (12, 35),
    ("purse", "leather"): (8, 25),
    ("tote", "leather"): (10, 30),
    ("backpack", "polyester"): (8, 18),
    ("canopy", "polyester"): (15, 40),
    ("gazebo", "polyester"): (18, 45),
    ("tent", "polyester"): (12, 35),
    ("folding chair", "polyester"): (6, 16),
    ("chair", "polyester"): (8, 20),
    ("chair", "steel"): (10, 24),
    ("laptop", "aluminum"): (200, 400),
    ("laptop", "plastic"): (200, 350),
}
_KIND_NOTE = {
    "lawn mower": "A gas lawn mower's footprint is mostly the fuel burned over its life, which is larger than the steel and plastic in the machine.",
    "laptop": "A typical laptop's manufacturing footprint is a few hundred kilograms of CO2e, before the electricity it uses.",
}
_TYPICAL = {
    "jacket": "polyester",
    "coat": "wool",
    "shirt": "cotton",
    "hoodie": "cotton",
    "running shoe": "polyester",
    "sneaker": "polyester",
    "handbag": "leather",
    "satchel": "leather",
    "purse": "leather",
    "tote": "leather",
    "backpack": "polyester",
    "canopy": "polyester",
    "gazebo": "polyester",
    "tent": "polyester",
    "folding chair": "polyester",
    "chair": "polyester",
    "laptop": "aluminum",
    "monitor": "plastic",
    "computer monitor": "plastic",
    "blood pressure monitor": "plastic",
    "baby monitor": "plastic",
    "headphones": "plastic",
    "lawn mower": "steel",
}
_COMPANY_FIGURE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(million|billion)?\s*(?:metric\s+)?(?:tonnes|tons)\b",
    re.IGNORECASE,
)


def with_outside_sources(estimate: dict, search, page_url: str = "") -> dict:
    """Add an outside product range and the company's reported footprint."""
    if search is None:
        return estimate
    sourced = dict(estimate)
    material = str(estimate.get("material") or "")
    kind = str(estimate.get("kind") or "")
    page_host = urlparse(page_url).netloc.removeprefix("www.")
    if material and kind:
        try:
            hits = search(f"{material} {kind} carbon footprint kg CO2e") or []
        except (RuntimeError, OSError, TypeError):
            hits = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            url = str(hit.get("url") or "").strip()
            host = urlparse(url).netloc.removeprefix("www.")
            blob = f"{hit.get('title') or ''} {hit.get('content') or ''}".lower()
            if not url.startswith("http") or (page_host and host == page_host):
                continue
            if not _mentions(blob, material) or not _mentions(blob, kind):
                continue
            match = _RANGE.search(blob)
            if match is None:
                continue
            low, high = int(match.group(1)), int(match.group(2))
            if high <= low or high > 2000:
                continue
            product_line = f"A {material} {kind} is typically about {low}–{high} kg CO2e."
            sourced["low"] = low
            sourced["high"] = high
            sourced["productHeadline"] = product_line
            sourced["source"] = {"url": url, "title": str(hit.get("title") or "Outside source")[:80]}
            sourced["estimated"] = True
            break
    return _company(sourced, _company_hits(search, sourced), page_host)


def estimate_footprint(name: str, page_text: str = "", specs: list | None = None) -> dict:
    """Estimate a product like this, then leave room for the company's footprint."""
    from backend.app.services.catalog.identity import brand_name

    named = _material(page_text, specs or [])
    kind = known_kind(name) or known_kind(page_text[:240])
    typical = _TYPICAL.get(kind, "")
    material = named or typical
    company = brand_name(name)
    company_line = (
        f"No outside source stated {company}'s company footprint."
        if company
        else "The brand was not clear enough to look up a company footprint."
    )
    base = _base(material)
    pair = _RANGES.get((kind, base))
    if pair:
        low, high = pair
        if named.startswith("recycled") or named.startswith("organic"):
            low = max(1, int(low * 0.8))
            high = max(low, int(high * 0.75))
        product_line = _product_line(material, kind, low, high, named)
        return _payload(material, kind, low, high, _mix(company_line, product_line), company, company_line, bool(named))
    if kind in _KIND_NOTE:
        product_line = _KIND_NOTE[kind]
        if material:
            product_line = f"{product_line} A {kind} like this is often made from {material}."
        return _payload(material, kind, None, None, _mix(company_line, product_line), company, company_line, bool(named))
    if material and kind:
        product_line = f"A {kind} like this is often made from {material}. That is not enough for a kilogram range."
        return _payload(material, kind, None, None, _mix(company_line, product_line), company, company_line, bool(named))
    if kind:
        return _payload("", kind, None, None, _mix(company_line, f"The materials for a {kind} like this were not clear enough for a kilogram range."), company, company_line, False)
    return _payload("", "", None, None, "The product type was not clear enough to estimate a footprint.", company, company_line, False)


def _product_line(material: str, kind: str, low: int, high: int, named: str) -> str:
    if named:
        return f"A {material} {kind} is typically about {low}–{high} kg CO2e."
    return f"A {kind} like this is often made from {material}, typically about {low}–{high} kg CO2e."


def _mix(company_line: str, product_line: str) -> str:
    if company_line and product_line:
        return f"{company_line} {product_line}"
    return company_line or product_line


def _company_hits(search, estimate: dict) -> list:
    company = str(estimate.get("company") or "")
    if not company:
        return []
    try:
        return search(f"{company} corporate greenhouse gas emissions") or []
    except (RuntimeError, OSError, TypeError):
        return []


def _company(estimate: dict, hits: list, page_host: str) -> dict:
    company = str(estimate.get("company") or "")
    product_line = str(estimate.get("productHeadline") or "")
    company_line = str(estimate.get("companyHeadline") or "")
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("url") or "").strip()
        host = urlparse(url).netloc.removeprefix("www.")
        blob = f"{hit.get('title') or ''} {hit.get('content') or ''}"
        if not url.startswith("http") or (page_host and host == page_host):
            continue
        if company.lower() not in blob.lower():
            continue
        match = _COMPANY_FIGURE.search(blob)
        if match is None:
            continue
        scale = f" {match.group(2).lower()}" if match.group(2) else ""
        company_line = f"{company}'s reported company footprint is about {match.group(1)}{scale} tonnes of CO2e."
        estimate["companySource"] = {"url": url, "title": str(hit.get("title") or "Company footprint")[:80]}
        break
    estimate["companyHeadline"] = company_line
    estimate["headline"] = _mix(company_line, product_line)
    return estimate


def _payload(
    material: str,
    kind: str,
    low,
    high,
    headline: str,
    company: str = "",
    company_line: str = "",
    named: bool = False,
) -> dict:
    product_line = headline
    if company_line and headline.startswith(company_line):
        product_line = headline[len(company_line) :].strip()
    estimated = bool(low or (material and kind) or kind in _KIND_NOTE)
    return {
        "material": material,
        "kind": kind,
        "low": low,
        "high": high,
        "company": company,
        "companyHeadline": company_line,
        "productHeadline": product_line,
        "headline": headline,
        "namedMaterial": named,
        "detail": (
            "The product range is an estimate for this kind of item. "
            "The company line is that company's footprint, not a measurement of this listing."
            if estimated
            else "The product type was not clear enough to estimate a footprint."
        ),
        "estimated": estimated,
    }


def _material(page_text: str, specs: list) -> str:
    chunks = [page_text or ""]
    for spec in specs:
        label = str(spec.get("label") or "")
        if label.lower() in {"material", "fabric", ""}:
            chunks.append(str(spec.get("value") or ""))
    haystack = " ".join(chunks).lower()
    for word in _MATERIALS:
        if re.search(rf"\b{re.escape(word)}\b", haystack):
            return word
    return ""


def _mentions(text: str, phrase: str) -> bool:
    return all(re.search(rf"\b{re.escape(word)}s?\b", text) for word in phrase.split())


def _base(material: str) -> str:
    for word in ("wool", "cotton", "polyester", "nylon", "leather", "linen", "hemp", "aluminum", "plastic", "steel"):
        if word in material:
            return word
    return material
