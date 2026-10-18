"""Extraction of product fine print and linked policy documents."""

import re

import pytest

from backend.app.services.fine_print.extraction import FinePrintExtractor

SOURCE = "https://shop.example/products/jacket"
RETURN_POLICY = "https://shop.example/help/returns"
WARRANTY = "https://shop.example/help/warranty"
OTHER_SITE = "https://ads.example/promo"
SIMILAR_PRODUCT = "https://shop.example/products/hat"

PAGES = {
    SOURCE: """
        <html><body>
          <a href="/help/returns">Return policy</a>
          <a href="https://shop.example/help/warranty">Warranty</a>
          <a href="https://ads.example/promo">Sponsored offer</a>
          <a href="/products/hat">Similar jacket</a>
          <a href="/cart">Cart</a>
          <p>Shell is 100% polyester. Final sale items cannot be returned. A 15% restocking fee applies to opened goods.</p>
        </body></html>
    """,
    RETURN_POLICY: """
        <html><body>
          <p>Items may be returned within 30 days. Final sale items are excluded.</p>
        </body></html>
    """,
    WARRANTY: """
        <html><body>
          <p>This limited warranty excludes normal wear, misuse, and commercial use.</p>
        </body></html>
    """,
}


def _visible_text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _fetch(url: str) -> str | None:
    return PAGES.get(url)


def test_extract_collects_product_text_and_policy_documents():
    result = FinePrintExtractor(fetch=_fetch, extract_html=_visible_text).extract(SOURCE)

    assert "100% polyester" in result.page_text
    assert "15% restocking fee" in result.page_text

    documents = {str(document.url).rstrip("/"): document for document in result.documents}
    assert set(documents) == {RETURN_POLICY, WARRANTY}
    assert "30 days" in documents[RETURN_POLICY].extracted_text
    assert "commercial use" in documents[WARRANTY].extracted_text
    assert OTHER_SITE not in documents
    assert SIMILAR_PRODUCT not in documents


def test_extract_keeps_one_copy_of_the_same_policy():
    pages = {
        SOURCE: """
            <html><body>
              <a href="https://shop.example/help/returns?nav=header">Return policy</a>
              <a href="https://www.shop.example/help/returns?nav=footer">Returns</a>
              <a href="https://shop.example/help/shipping?utm_source=footer">Shipping</a>
              <a href="https://shop.example/help/shipping?bvCategory=shipping">Shipping details</a>
            </body></html>
        """,
        "https://shop.example/help/returns?nav=header": "<html><body><p>30 day returns.</p></body></html>",
        "https://www.shop.example/help/returns?nav=footer": "<html><body><p>Duplicate return policy.</p></body></html>",
        "https://shop.example/help/shipping?utm_source=footer": "<html><body><p>Shipping fees apply.</p></body></html>",
        "https://shop.example/help/shipping?bvCategory=shipping": "<html><body><p>Duplicate shipping policy.</p></body></html>",
    }

    result = FinePrintExtractor(
        fetch=pages.get,
        extract_html=_visible_text,
    ).extract(SOURCE)

    assert [str(document.url).rstrip("/") for document in result.documents] == [
        "https://shop.example/help/returns?nav=header",
        "https://shop.example/help/shipping?utm_source=footer",
    ]
    assert "Duplicate return policy." not in " ".join(
        document.extracted_text for document in result.documents
    )


def test_extract_raises_when_the_page_cannot_be_fetched():
    extractor = FinePrintExtractor(fetch=lambda url: None, extract_html=_visible_text)

    with pytest.raises(RuntimeError, match="Failed to fetch URL"):
        extractor.extract(SOURCE)


def test_extract_skips_policy_links_that_cannot_be_read():
    def fetch(url: str) -> str | None:
        if url == WARRANTY:
            return None
        return PAGES.get(url)

    result = FinePrintExtractor(fetch=fetch, extract_html=_visible_text).extract(SOURCE)

    assert {str(document.url).rstrip("/") for document in result.documents} == {RETURN_POLICY}
    assert "15% restocking fee" in result.page_text


def test_extract_keeps_a_return_sentence_the_main_reader_skipped():
    html = """
        <html><body>
          <div class="hero">Shop the collection.</div>
          <p>Our standard return policy is 30 days for unworn items with the original tags attached.</p>
        </body></html>
    """

    pages = {SOURCE: "<html><body><a href='/help/returns'>Return policy</a><p>Shop the collection.</p></body></html>", RETURN_POLICY: html}

    result = FinePrintExtractor(
        fetch=pages.get,
        extract_html=lambda page: "Shop the collection.",
    ).extract(SOURCE)

    document = result.documents[0]
    assert "30 days" in document.extracted_text
    assert "30 days" not in result.page_text
