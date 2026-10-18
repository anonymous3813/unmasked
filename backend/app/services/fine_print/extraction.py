"""Policy document extraction for fine-print risk analysis."""

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

from trafilatura import extract, fetch_url

from backend.app.models.fine_print import FinePrintExtraction, PolicyDocument

# Lower rank is kept first. Returns, fees, and warranties outrank generic legal links.
_POLICY_HINTS = (
    ("return", 0),
    ("refund", 0),
    ("restock", 0),
    ("exchange", 1),
    ("warranty", 1),
    ("guarantee", 1),
    ("cancel", 2),
    ("subscription", 2),
    ("fee", 2),
    ("shipping", 3),
    ("delivery", 3),
    ("terms", 4),
    ("disclosure", 4),
    ("privacy", 5),
    ("legal", 5),
    ("policy", 6),
)
_MAX_DOCUMENTS = 8
_POLICY_LINE = re.compile(
    r"\b(?:return|refund|exchange|warranty|restock|damage)\b",
    re.IGNORECASE,
)


class _AnchorCollector(HTMLParser):
    """Collect anchor hrefs and their visible labels."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text)))
            self._href = None
            self._text = []


class FinePrintExtractor:
    """Pull product details and the policy pages shoppers usually miss.

    Trafilatura reads the source page, including specification tables. Links
    on that same site for returns, warranties, shipping, cancellation, fees,
    and similar terms are fetched as separate documents.
    """

    def __init__(self, fetch=None, extract_html=None) -> None:
        self._fetch = fetch or fetch_url
        self._extract_html = extract_html or _extract_with_trafilatura

    def extract(self, url: str) -> FinePrintExtraction:
        """Extract one page and the fine-print documents linked from it."""
        retrieved_at = datetime.now(timezone.utc)
        html = self._fetch(url)
        if not html:
            raise RuntimeError(f"Failed to fetch URL: {url}")

        page_text = (self._extract_html(html) or "").strip()
        if not page_text:
            raise RuntimeError(f"Failed to extract text from URL: {url}")

        documents = [
            document
            for link in _policy_links(url, html)
            if (document := self._document_from_url(link, retrieved_at)) is not None
        ]
        return FinePrintExtraction(
            source_url=url,
            page_text=page_text,
            documents=documents,
            retrieved_at=retrieved_at,
        )

    def _document_from_url(self, url: str, retrieved_at: datetime) -> PolicyDocument | None:
        html = self._fetch(url)
        if not html:
            return None
        text = _read_text(html, self._extract_html)
        if not text:
            return None
        return PolicyDocument(url=url, extracted_text=text, retrieved_at=retrieved_at)


def _extract_with_trafilatura(html: str) -> str:
    text = extract(
        html,
        output_format="markdown",
        with_metadata=True,
        include_tables=True,
        favor_recall=True,
    )
    return text or ""


def _read_text(html: str, extract_html) -> str:
    text = (extract_html(html) or "").strip()
    missing = _missing_policy_sentences(html, text)
    if missing:
        text = f"{text}\n{missing}".strip()
    return text


def _missing_policy_sentences(html: str, extracted: str) -> str:
    """Keep return and warranty sentences the main extractor skipped."""
    known = " ".join(extracted.lower().split())
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", _plain_html(html)):
        cleaned = " ".join(sentence.split())
        if not _usable_policy_sentence(cleaned) or " ".join(cleaned.lower().split()) in known:
            continue
        kept.append(cleaned)
    return " ".join(kept[:4])


def _usable_policy_sentence(cleaned: str) -> bool:
    if len(cleaned) < 36 or len(cleaned) > 320 or "|" in cleaned:
        return False
    if cleaned.startswith("---") or "hostname:" in cleaned or "fingerprint:" in cleaned:
        return False
    return _POLICY_LINE.search(cleaned) is not None


def _plain_html(html: str) -> str:
    without_code = re.sub(
        r"<(script|style|noscript)\b[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", without_code)))


def _policy_links(page_url: str, html: str) -> list[str]:
    parser = _AnchorCollector()
    parser.feed(html)
    page_host = _host(page_url)
    page_key = _document_key(page_url)
    found: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for index, (href, label) in enumerate(parser.links):
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = _without_fragment(urljoin(page_url, href))
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or _host(absolute) != page_host:
            continue
        key = _document_key(absolute)
        rank = _policy_rank(label, parsed.path)
        if key == page_key or key in seen or rank is None:
            continue
        seen.add(key)
        found.append((rank, index, absolute))

    found.sort(key=lambda item: (item[0], item[1]))
    return [url for _, _, url in found[:_MAX_DOCUMENTS]]


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _without_fragment(url: str) -> str:
    return urldefrag(url).url


def _document_key(url: str) -> str:
    """Identity used to skip another link to the same policy path."""
    parsed = urlparse(_without_fragment(url))
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{_host(url)}{path}"


def _policy_rank(label: str, path: str) -> int | None:
    haystack = f"{label} {path}".lower()
    ranks = [rank for hint, rank in _POLICY_HINTS if hint in haystack]
    if not ranks:
        return None
    return min(ranks)
