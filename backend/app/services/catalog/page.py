"""Decide whether a URL is a product page the agent should read."""

import re
from urllib.parse import urlparse

_BLOCKED_HOSTS = {
    "google.com",
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "wikipedia.org",
    "github.com",
    "localhost",
    "127.0.0.1",
}
_LISTING = re.compile(
    r"/(?:search|cart|checkout|account|login|blog|help|category|categories|collections|browse|gp/browse)(?:/|$)|(?:^|/)s(?:/|$)",
    re.IGNORECASE,
)
_PRODUCT = re.compile(
    r"/(?:products|product|dp|gp/product|ip|itm|listing|item|p)/[^/?#]+",
    re.IGNORECASE,
)


def host_of(url: str) -> str:
    """Return the hostname without a leading www or a port."""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def is_blocked(url: str) -> bool:
    """Search engines, social sites, and this computer are not product pages."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return True
    host = host_of(url)
    return any(host == blocked or host.endswith("." + blocked) for blocked in _BLOCKED_HOSTS)


def is_listing(url: str) -> bool:
    """Search, cart, and category paths are not one product."""
    return _LISTING.search(urlparse(url).path or "/") is not None


def is_product_url(url: str) -> bool:
    """True when the path is a product listing on a store."""
    if is_blocked(url) or is_listing(url):
        return False
    return _PRODUCT.search(urlparse(url).path or "/") is not None


def accepts_page(url: str, product_page: bool = False) -> bool:
    """The agent reads a page only when it is one product, not a search or article."""
    if is_blocked(url) or is_listing(url):
        return False
    return bool(product_page) or is_product_url(url)
