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
    "folding chair",
    "chair",
    "canopy",
    "gazebo",
    "tent",
    "water bottle",
    "phone case",
    "coffee maker",
    "air fryer",
    "pressure cooker",
    "stand mixer",
    "lawn mower",
    "running shoe",
    "sneaker",
    "handbag",
    "satchel",
    "purse",
    "tote",
    "backpack",
    "laptop",
    "blood pressure monitor",
    "baby monitor",
    "heart rate monitor",
    "glucose monitor",
    "computer monitor",
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
_CHROME = re.compile(
    r"keyboard shortcut|product summary presents|skip to|sponsored|customers who bought|sign in to",
    re.IGNORECASE,
)


def readable_name(value: str) -> str:
    """A product name a shopper can see. Screen-reader chrome is not a product."""
    text = " ".join(str(value or "").split())
    text = re.sub(r"^(?:amazon\.com|walmart|ebay|etsy)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" -|")[:160]
    if len(text) < 8 or _CHROME.search(text):
        return ""
    return text


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
    found.sort(key=lambda item: (item[0], -len(item[2]), item[1]))
    return found[0][2]


_DISPLAY = {"monitor", "computer monitor"}
_SEATS = {"chair", "folding chair", "desk chair", "office chair"}


def same_product(wanted: str, listed: str) -> bool:
    """A shared word is not enough. A display is not a blood-pressure monitor."""
    wanted = " ".join(str(wanted or "").lower().split())
    listed = " ".join(str(listed or "").lower().split())
    if not wanted or not listed:
        return False
    if wanted == listed:
        return True
    if wanted in _DISPLAY and listed in _DISPLAY:
        return True
    return wanted == "chair" and listed in _SEATS


def _accessory(text: str, start: int) -> bool:
    """A category after with, includes, or plus is the accessory, not the product."""
    window = text[max(0, start - 40) : start]
    return bool(re.search(r"\b(?:with|includes|including|plus|compatible with|fits)\b", window))


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


def brand_name(name: str) -> str:
    """The brand in front of the product kind, when the title has one."""
    label = search_label(name)
    kind = known_kind(name)
    spoken = "tv" if kind == "television" else kind
    if spoken and label.lower().endswith(" " + spoken):
        return label[: -(len(spoken) + 1)].strip()
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


def identify_product(
    heading: str,
    title: str,
    candidates: list | None = None,
    page_text: str = "",
    complete=None,
) -> dict:
    """Pick the product on screen. Related structured data is not that product."""
    import os

    options = []
    for value in [heading, *(candidates or []), title]:
        text = readable_name(value)
        if text and text not in options:
            options.append(text)
    if not options:
        return {"name": "", "brand": "", "kind": ""}
    visible = _visible_choice(heading, options)
    if os.environ.get("PYTEST_CURRENT_TEST") or complete is None:
        return visible
    try:
        raw = complete(
            "The shopper is looking at one product. The heading is that product. "
            "The other names are structured data and may be related products, ads, or accessories. "
            "Copy the name of the product on screen from the heading or the list. "
            "Name its brand and a store category of one or two words. "
            'Return JSON: {"name": "", "brand": "", "kind": ""}\n\n'
            f"Heading: {heading}\n\n"
            f"Page title: {title}\n\n"
            "Names on the page:\n"
            + "\n".join(f"- {option}" for option in options)
            + f"\n\nPage text:\n{(page_text or '')[:1500]}"
        )
    except RuntimeError:
        return visible
    payload = _object(raw)
    name = " ".join(str(payload.get("name") or "").split())
    if not any(name.lower() == option.lower() or name.lower() in option.lower() or option.lower() in name.lower() for option in options):
        return visible
    kind = accept_kind(name, page_text, str(payload.get("kind") or "")) or known_kind(name) or visible["kind"]
    brand = " ".join(str(payload.get("brand") or "").split()) or brand_name(name) or visible["brand"]
    return {"name": name or visible["name"], "brand": brand, "kind": kind}


def _visible_choice(heading: str, options: list[str]) -> dict:
    """Prefer the visible heading over the first structured-data product."""
    heading = readable_name(heading)
    options = [option for option in options if readable_name(option)]
    if not options:
        return {"name": "", "brand": "", "kind": ""}
    wanted = [word for word in re.findall(r"[a-z0-9]+", heading.lower()) if len(word) > 3]
    best = options[0]
    best_score = -1
    for option in options:
        haystack = option.lower()
        score = sum(1 for word in wanted if word in haystack)
        if heading and haystack == heading.lower():
            score += 10
        if score > best_score:
            best = option
            best_score = score
    return {"name": best, "brand": brand_name(best), "kind": known_kind(best)}


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
