"""The product kind used for similar listings and outside carbon searches."""

import json
import re

_KINDS = (
    "shower head",
    "headphones",
    "mattress",
    "bed frame",
    "running shoe",
    "desk chair",
    "office chair",
    "water bottle",
    "phone case",
    "coffee maker",
    "air fryer",
    "pressure cooker",
    "stand mixer",
    "lawn mower",
    "running shoe",
    "sneaker",
    "backpack",
    "laptop",
    "monitor",
    "keyboard",
    "speaker",
    "earbuds",
    "vacuum",
    "blender",
    "pillow",
    "towel",
    "hoodie",
    "shirt",
    "dress",
    "watch",
    "lamp",
    "sofa",
    "couch",
    "boot",
    "sandal",
    "jacket",
    "coat",
    "television",
    "tablet",
    "camera",
    "refrigerator",
    "washer",
    "dryer",
    "printer",
    "bicycle",
    "grill",
    "drill",
)
_KIND_SKIP = {
    "smart",
    "pro",
    "wireless",
    "cordless",
    "portable",
    "electric",
    "digital",
    "premium",
    "original",
    "new",
    "best",
    "series",
    "inch",
    "class",
}
_GENERIC = {
    "mens",
    "men",
    "womens",
    "women",
    "the",
    "and",
    "for",
    "with",
    "new",
    "size",
    "pack",
    "set",
    "inch",
    "class",
}


def known_kind(name: str) -> str:
    """The product category in the title. An accessory named later does not replace it."""
    lowered = name.lower().replace("'", "")
    found: list[tuple[bool, int, str]] = []

    def add(phrase: str, start: int) -> None:
        found.append((_accessory(lowered, start), start, phrase))

    for match in re.finditer(r"lawn\s*mowers?", lowered):
        add("lawn mower", match.start())
    runner = re.search(r"tree\s+runners?|\brunners?\b", lowered)
    if runner:
        add("running shoe", runner.start())
    for match in re.finditer(r"\btvs?\b|\btelevision\b", lowered):
        add("television", match.start())
    for phrase in set(_KINDS):
        if phrase in {"lawn mower", "television"}:
            continue
        pattern = r"\b" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"s?\b"
        for match in re.finditer(pattern, lowered):
            add(phrase, match.start())
    if not found:
        return ""
    found.sort()
    return found[0][2]


def _accessory(text: str, start: int) -> bool:
    """A category after with, includes, or plus is the accessory, not the product."""
    window = text[max(0, start - 32) : start]
    return bool(re.search(r"\b(?:with|includes|including|plus|compatible with|fits)\s+$", window))


def accept_kind(name: str, text: str, guessed: str) -> str:
    """Keep a category the product title names. A guess has to be written on the page."""
    named = known_kind(name)
    if named:
        return named
    words = [word for word in str(guessed or "").lower().split() if word]
    if not words:
        return ""
    haystack = f"{name}\n{text}".lower()
    if all(re.search(rf"\b{re.escape(word)}s?\b", haystack) for word in words):
        return " ".join(words[:2])
    return ""


def search_label(name: str) -> str:
    """Brand plus category, so a long model title does not hide the carbon search."""
    kind = known_kind(name)
    brand = ""
    for token in re.findall(r"[A-Za-z0-9]+", name):
        lowered = token.lower()
        if lowered in _GENERIC or len(lowered) < 3:
            continue
        if kind and lowered in kind.split():
            continue
        brand = token
        break
    if brand and kind:
        spoken = "tv" if kind == "television" else kind
        return f"{brand} {spoken}"
    if kind:
        return "tv" if kind == "television" else kind
    words = [token for token in re.findall(r"[A-Za-z0-9]+", name) if token.lower() not in _GENERIC and len(token) > 2]
    return " ".join(words[:4])


def mentions_product(label: str, text: str) -> bool:
    """A source has to name the brand when we know it, not only the product category."""
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", label.lower())
        if (len(word) > 3 or word == "tv") and word not in _GENERIC
    ]
    if not words:
        return False
    haystack = (text or "").lower()
    kind_words = set(known_kind(label).replace("television", "tv").split())
    brand = next((word for word in words if word not in kind_words), "")
    if brand and brand not in haystack:
        return False
    needed = words[:4]
    return sum(1 for word in needed if word in haystack) >= min(2, len(needed))


def kind_from_model(name: str, page_text: str, complete) -> str:
    """Ask the agent for a store category. Adjectives and brands are removed."""
    raw = complete(
        "Name the store category of the product on this page. "
        "Use one or two words a shopper would search, such as lawn mower, television, or headphones. "
        "Do not include the brand, color, size, or words such as smart, pro, or wireless. "
        'Return JSON: {"kind": "the category"}\n\n'
        f"Title: {name}\n\n"
        f"Page text:\n{(page_text or '')[:2000]}"
    )
    payload = _object(raw)
    words = [
        word
        for word in re.findall(r"[a-z]+", str(payload.get("kind") or "").lower())
        if len(word) > 2 and word not in _KIND_SKIP
    ]
    return " ".join(words[:2])


def _object(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
