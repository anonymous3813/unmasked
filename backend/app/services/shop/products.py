"""Products from other stores that fit the item the shopper asked for."""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from backend.app.integrations.tavily_client import TavilyClient

_ASK = re.compile(
    r"\b(?:find|show|get|search(?: for)?|look for)\s+(?:me\s+)?(?:an?\s+|some\s+)?([a-z][a-z0-9\- ]{1,40})",
    re.IGNORECASE,
)
_WHAT = re.compile(
    r"\b(?:what|which)\s+(?:an?\s+|some\s+)?([a-z][a-z0-9\- ]{1,40}?)\s+"
    r"(?:goes|go|works|work|fits|fit|pairs|pair|matches|match|is compatible|are compatible)\b",
    re.IGNORECASE,
)
_BARE = re.compile(
    r"\b(?:compatible products?|what goes with|what should i (?:get|buy) with|pairs with this|goes with this|to go with this)\b",
    re.IGNORECASE,
)
_STOP = re.compile(
    r"\b(?:that|which|to|for|with|works|work|goes|go|fits|fit|pairs|pair|matches|match)\b",
    re.IGNORECASE,
)
_SIZE = re.compile(r"\b(twin|full|queen|king|california king)\b", re.IGNORECASE)
_PRICE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{2}))?")
_IMAGE = re.compile(r"https://[^ \]'\"<>]+\.(?:jpg|jpeg|png|webp)", re.IGNORECASE)
_SKIP = {
    "mattress": ("protector", "pump", "topper", "sheet", "pillowcase", "foundation", "frame", "headboard"),
    "lawn mower": ("cover", "blade", "bag", "battery", "oil", "filter", "wheel", "tire", "hose", "doll", "miniature", "toy", "prop"),
    "running shoe": ("sock", "insole", "lace", "cleaner"),
}
_GENERIC = {"product", "products", "something", "item", "items", "one", "stuff", "things"}
_PAIRS = (
    (re.compile(r"bed frame|platform bed|bedframe", re.IGNORECASE), "mattress"),
    (re.compile(r"\bmattress\b", re.IGNORECASE), "fitted sheet"),
    (re.compile(r"sneaker|running shoe|tree runner", re.IGNORECASE), "sock"),
    (re.compile(r"\bjacket\b|\bcoat\b", re.IGNORECASE), "scarf"),
    (re.compile(r"\bsofa\b|\bcouch\b", re.IGNORECASE), "throw pillow"),
    (re.compile(r"\bdesk\b", re.IGNORECASE), "desk chair"),
)


def requested_item(question: str, title: str = "") -> str | None:
    """Return the product the shopper asked to find, or nothing for other questions."""
    explicit = _explicit(question or "")
    if explicit and explicit not in _GENERIC:
        return explicit
    if explicit in _GENERIC or _BARE.search(question or ""):
        return _inferred(title)
    return None


def _explicit(question: str) -> str | None:
    match = _WHAT.search(question) or _ASK.search(question)
    if match is None:
        return None
    words = []
    for word in match.group(1).split():
        if _STOP.match(word):
            break
        words.append(word)
    item = " ".join(words).strip(" -")
    return item or None


def _inferred(title: str) -> str | None:
    for pattern, item in _PAIRS:
        if pattern.search(title or ""):
            return item
    return None


_BLOCKED_HOSTS = {
    "youtube.com",
    "facebook.com",
    "reddit.com",
    "mapquest.com",
    "wikipedia.org",
    "pinterest.com",
    "instagram.com",
    "tiktok.com",
}
_STORE_QUERIES = (
    ("walmart.com", "site:walmart.com/ip"),
    ("amazon.com", "site:amazon.com/dp"),
    ("etsy.com", "site:etsy.com/listing"),
    ("homedepot.com", "site:homedepot.com/p/"),
)
_STORE_NAMES = {
    "walmart.com": "Walmart",
    "amazon.com": "Amazon",
    "target.com": "Target",
    "wayfair.com": "Wayfair",
    "ebay.com": "eBay",
    "homedepot.com": "Home Depot",
    "lowes.com": "Lowe's",
    "etsy.com": "Etsy",
}


def find_products(
    item: str,
    title: str = "",
    page_text: str = "",
    current_url: str = "",
    search=None,
    extract=None,
    query_prefix: str = "",
) -> list[dict]:
    """Return priced listings for the requested item, one per store."""
    search = search or _search
    extract = extract or _extract
    size = _size(title, page_text)
    current_host = _host(current_url)
    queries = [f"{query_prefix} {size} {item} {hint}".strip() for _host, hint in _STORE_QUERIES]
    hits = []
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        for batch in pool.map(lambda query: _safe_search(search, query), queries):
            hits.extend(batch)
    _fill_prices(item, hits, current_host, extract)
    cards = []
    seen = set()
    for hit in hits:
        card = _card(item, hit, current_host)
        if card is None or not card.get("imageUrl") or card["store"] in seen:
            continue
        seen.add(card["store"])
        cards.append(card)
        if len(cards) == 6:
            break
    return cards


def _safe_search(search, query: str) -> list[dict]:
    try:
        found = search(query)
    except (RuntimeError, OSError):
        return []
    return found if isinstance(found, list) else []


def _search(query: str) -> list[dict]:
    return TavilyClient().search(query, max_results=4, search_depth="basic", include_images=True)


def _extract(urls: list[str]) -> list[dict]:
    return TavilyClient().extract(urls)


def _fill_prices(item: str, hits: list[dict], current_host: str, extract) -> None:
    missing = []
    for hit in hits:
        if _candidate(item, hit, current_host) and (_price(hit) is None or not _image(hit)):
            missing.append(hit)
    if not missing:
        return
    try:
        pages = extract([str(hit.get("url") or "") for hit in missing[:4]])
    except (RuntimeError, OSError, TypeError):
        return
    by_url = {str(page.get("url") or "").split("?")[0]: page for page in pages}
    for hit in missing:
        page = by_url.get(str(hit.get("url") or "").split("?")[0])
        if page is None:
            continue
        hit["raw_content"] = str(page.get("raw_content") or page.get("content") or "")


def _candidate(item: str, hit: dict, current_host: str) -> bool:
    url = str(hit.get("url") or "").split("?")[0]
    host = _host(url)
    if not host or host == current_host or host in _BLOCKED_HOSTS or not _product_page(url):
        return False
    name = _name(str(hit.get("title") or ""))
    return _same_kind(item, name)


def _card(item: str, hit: dict, current_host: str) -> dict | None:
    if not _candidate(item, hit, current_host):
        return None
    url = str(hit.get("url") or "").split("?")[0]
    host = _host(url)
    name = _name(str(hit.get("title") or ""))
    if not _sellable(name):
        return None
    if re.search(r"\bshoes?\b", item, re.I) and not re.search(r"\b(shoes?|sneakers?|runners?)\b", name, re.I):
        return None
    blob = f"{name} {hit.get('content') or ''}".lower()
    if any(word in blob for word in _SKIP.get(_stem(item.lower()), ())):
        return None
    weak = [word for word in ("cover", "plate", "switch", "sticker", "wallpaper") if word not in item.lower()]
    if any(word in name.lower() for word in weak):
        return None
    price = _price(hit)
    if price is None:
        return None
    return {
        "name": name,
        "store": _STORE_NAMES.get(host, host.split(".")[0].title()),
        "price": price,
        "url": url,
        "imageUrl": _image(hit),
        "message": " ".join(str(hit.get("content") or "").split())[:180],
    }


_WORD_ALIASES = {
    "wooden": ("wood",),
    "wood": ("wooden",),
    "plank": ("board",),
    "board": ("plank",),
}


def _same_kind(item: str, name: str) -> bool:
    """The listing title has to be this product, not a page that merely mentions it."""
    if not _matches(item, name.lower()):
        return False
    from backend.app.services.catalog.identity import known_kind

    listed = known_kind(name)
    wanted = known_kind(item) or item.lower()
    if not listed:
        return True
    return listed == wanted or listed in wanted or wanted in listed


def _matches(item: str, blob: str) -> bool:
    if item == "television":
        return bool(re.search(r"\btvs?\b|television", blob))
    words = [_stem(word) for word in item.lower().split() if len(_stem(word)) > 2]
    return all(_word_in(word, blob) for word in words)


def _word_in(word: str, blob: str) -> bool:
    options = (word, *_WORD_ALIASES.get(word, ()))
    return any(re.search(rf"\b{re.escape(option)}s?\b", blob) for option in options)


def _stem(word: str) -> str:
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _product_page(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    if path.count("/") < 1 and not path:
        return False
    lowered = path.lower()
    if lowered.endswith("/s") or any(
        piece in lowered
        for piece in (
            "/search",
            "/forum",
            "/blog",
            "/category",
            "/collections/",
            "/collection/",
            "/b/",
            "/c/",
            "/market/",
            "/guides/",
            "/review",
            "/deals",
        )
    ):
        return False
    return any(piece in lowered for piece in ("/products/", "/product/", "/ip/", "/dp/", "/p/", "/listing/", "/itm/"))


_NOT_SELLABLE = re.compile(
    r"\b(art print|poster|scripture|sticker|digital download|svg|gift card|wallpaper)\b",
    re.IGNORECASE,
)
_STORE_ONLY = {"amazon.com", "walmart.com", "etsy.com", "ebay.com", "homedepot.com"}


def _sellable(name: str) -> bool:
    """Keep a store listing and skip titles that are a store name or a print."""
    clean = " ".join(name.lower().split())
    if len(clean) < 8 or clean in _STORE_ONLY or _NOT_SELLABLE.search(clean):
        return False
    return True


def _name(title: str) -> str:
    name = re.sub(r"^Amazon\.com:\s*", "", title)
    name = re.split(r"\s+[|\-–:]\s+", name, maxsplit=1)[0].strip()
    return name[:90] or title[:90]


def _price(hit: dict) -> str | None:
    text = " ".join(str(hit.get(key) or "") for key in ("title", "content", "raw_content"))
    for match in _PRICE.finditer(text):
        dollars = match.group(1).replace(",", "")
        cents = match.group(2) or "00"
        amount = int(dollars)
        if amount < 3 or amount > 5000:
            continue
        return f"{amount}.{cents}"
    return None


def _image(hit: dict) -> str:
    direct = str(hit.get("image") or hit.get("imageUrl") or "").strip()
    if direct.startswith("http"):
        return direct
    raw = str(hit.get("raw_content") or "")
    for url in _IMAGE.findall(raw):
        lowered = url.lower()
        if any(word in lowered for word in ("/dfw/", "logo", "sprite", "icon", "badge", "smile", "pixel")):
            continue
        return url
    return ""


def _size(title: str, page_text: str) -> str:
    match = _SIZE.search(f"{title} {page_text[:2000]}")
    return match.group(1).lower() if match else ""


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) > 2 and parts[0] in {"us", "uk", "ca", "m"}:
        host = ".".join(parts[1:])
    return host
