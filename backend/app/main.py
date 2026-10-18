import io
import os
import re
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, HttpUrl

from backend.app.demo.report import demo_answer, demo_report, watch_policy

from backend.app.services.registry.log import record, snapshot
from backend.app.services.catalog.page import accepts_page
from backend.app.services.shop.products import find_products, requested_item
from backend.app.services.shop.tax import tax_note
from backend.app.services.shop.agent import answer_question
from backend.app.integrations.photon_line import send_intro
from backend.app.services.shop.cart import assistant, orders_answer, purchase, refresh_delivery
from backend.app.services.shop.wishlist import add_wishlist, wishlist
from backend.app.services.shop.inbox import inbox, place_call, send_message
from backend.app.services.shop.marks import offer_alternatives, page_report
from backend.app.integrations.openai_client import OpenAIClient
from backend.app.services.catalog.report import build_report, look_at_page

ROOT = Path(__file__).resolve().parents[2]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load purchases that were saved in Supabase."""
    from backend.app.integrations.supabase_store import hydrate

    hydrate()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


class PageNotesRequest(BaseModel):
    url: HttpUrl
    listed_price: str | None = None
    postal_code: str | None = None
    page_text: str = ""
    record: dict = {}
    product_page: bool = False


class TaxRequest(BaseModel):
    amount: str
    postal_code: str


class AskRequest(BaseModel):
    question: str
    url: HttpUrl
    title: str | None = None
    page_text: str = ""
    notes: list[dict] = []
    visits: list[dict] = []
    dossier: dict = {}
    outside: dict = {}
    product_page: bool = False


class CartItem(BaseModel):
    name: str
    url: HttpUrl
    store: str
    price: str
    imageUrl: str = ""
    environmentScore: int | None = None
    materials: str = ""
    message: str = ""
    quotation: str = ""


class CheckoutRequest(BaseModel):
    items: list[CartItem]


class InboxMessage(BaseModel):
    text: str
    cart: list[dict] = []
    notes: list[dict] = []


class InboxCall(BaseModel):
    cart: list[dict] = []
    notes: list[dict] = []


class IntroRequest(BaseModel):
    text: str = ""


class AlternativesRequest(BaseModel):
    name: str = ""
    url: str = ""
    page_text: str = ""
    listed_price: str | None = None


class WishlistItem(BaseModel):
    name: str
    url: str
    store: str = ""
    price: str = ""
    imageUrl: str = ""
    environmentScore: int | None = None


class DemoQuestion(BaseModel):
    question: str


class DemoMonitor(BaseModel):
    product: str = "Harbor Headphones"


@app.get("/")
def home():
    """Serve the landing page, extension download, and agent registry."""
    return FileResponse(ROOT / "registry-site" / "index.html")


@app.get("/registry")
def read_registry():
    """Return the assistant's messages, calls, orders, and page checks."""
    return snapshot()


@app.get("/extension.zip")
def download_extension():
    """Download the unpacked Chrome extension."""
    folder = ROOT / "chrome-extension"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name in {"preview.html", ".DS_Store"}:
                continue
            archive.write(path, Path("unmasked") / path.relative_to(folder))
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=unmasked-extension.zip"},
    )


@app.get("/demo")
def demo_page():
    """Serve the clickable headphones demo."""
    return FileResponse(ROOT / "registry-site" / "demo.html")


@app.get("/demo/report")
def read_demo_report():
    """Return the seeded product report. Every fact is labeled as demo data."""
    return demo_report()


@app.post("/demo/ask")
def ask_demo(body: DemoQuestion):
    """Answer from the seeded report and the demo shopper's prior return."""
    return {"answer": demo_answer(body.question)}


@app.post("/demo/monitors")
def create_demo_monitor(body: DemoMonitor):
    """Opt in to a demo return-policy watch. No Photon message is sent."""
    return watch_policy(body.product)


@app.post("/page-notes")
def page_notes(body: PageNotesRequest):
    """Return the price, policy, and product marks for one product page."""
    report = page_report(
        str(body.url),
        body.listed_price,
        body.postal_code,
        body.page_text,
        body.record,
        body.product_page,
    )
    titles = [
        str(note.get("title") or note.get("kind") or "")
        for note in report.get("notes") or []
    ]
    titles = [title for title in titles if title]
    record(
        "page",
        urlparse(str(body.url)).netloc or "Product page",
        "; ".join(titles) or "No policy notes on this page.",
        str(body.url),
    )
    dossier = report.get("dossier") or {}
    report["report"] = _shopping_report(
        name=str(dossier.get("name") or (body.record or {}).get("name") or ""),
        url=str(body.url),
        dossier=dossier,
        outside=report.get("outside") or {},
        notes=report.get("notes") or [],
        page_text=body.page_text,
    )
    return report


@app.post("/sales-tax")
def sales_tax(body: TaxRequest):
    """Return the location tax mark for one listed price."""
    note = tax_note(body.amount, body.postal_code)
    return {"note": note}


@app.post("/intro")
def intro(body: IntroRequest):
    """Send the first product summary by text, including when the page had no policy changes."""
    result = send_intro(body.text)
    detail = "Delivered." if result.get("sent") else str(result.get("reason") or "Not delivered.")
    record("intro", "First text", detail)
    return result


@app.get("/assistant")
def assistant_profile():
    """Return the name and phone number shown in the chat."""
    return assistant()


@app.post("/ask")
def ask(body: AskRequest):
    """Answer one product question with the shopper's agent."""
    question = body.question.strip()
    if not accepts_page(str(body.url), body.product_page):
        answer = "I only read product pages. Open a product and ask me there."
        return _asked(body, answer, [])
    item = requested_item(question, body.title or "")
    if item:
        products = find_products(item, body.title or "", body.page_text, str(body.url))
        if products:
            stores = _store_list(list(dict.fromkeys(product["store"] for product in products)))
            answer = f"These {item} listings are from {stores}. Add any of them to your cart."
        else:
            answer = f"I couldn't find a priced listing for {item} at another store."
        record("ask", question, answer, str(body.url))
        return _asked(body, answer, products)
    remembered = orders_answer(question)
    if remembered is not None:
        record("ask", question, remembered, str(body.url))
        return _asked(body, remembered, [])
    answer = answer_question(
        question,
        title=body.title or "",
        page_text=body.page_text,
        notes=body.notes,
        visits=body.visits,
        dossier=body.dossier,
    )
    products = []
    if re.search(r"\b(greener|alternative|alternatives|better value|better reviewed|eco|environment)\b", question, re.I):
        products = offer_alternatives(body.title or "", str(body.url), body.page_text).get("products") or []
    record("ask", question, answer, str(body.url))
    return _asked(body, answer, products)


@app.get("/inbox")
def read_inbox():
    """Return the assistant's messages, calls, and orders."""
    return inbox()


@app.post("/inbox/message")
def inbox_message(body: InboxMessage):
    """Message the assistant about the cart, orders, or this product."""
    return send_message(body.text, body.cart, notes=body.notes)


@app.post("/inbox/call")
def inbox_call(body: InboxCall):
    """Call the assistant and hear the cart and orders."""
    return place_call(body.cart, notes=body.notes)


@app.post("/cart/checkout")
def checkout(body: CheckoutRequest):
    """Record every cart item as an order on the assistant's profile."""
    items = [item.model_dump(mode="json") for item in body.items]
    return purchase(items)


@app.get("/wishlist")
def read_wishlist():
    """Return products the shopper saved from the agent's recommendations."""
    return wishlist()


@app.post("/wishlist")
def save_wishlist_item(body: WishlistItem):
    """Save a recommended product and text the shopper on Photon 2.0."""
    return add_wishlist(body.model_dump())


@app.get("/purchases")
def purchases():
    """Return bought products, their environment scores, the shopper's footprint, and delivery status."""
    return refresh_delivery()


@app.post("/alternatives")
def alternatives(body: AlternativesRequest):
    """Return greener, better-reviewed, and better-value listings for the product on screen."""
    return offer_alternatives(body.name, body.url, body.page_text, body.listed_price)


def _shopping_report(**kwargs) -> dict:
    grounded = build_report(**kwargs)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return grounded
    return look_at_page(grounded, kwargs.get("page_text") or "", complete=OpenAIClient().complete)


def _asked(body: AskRequest, answer: str, products: list) -> dict:
    dossier = body.dossier or {}
    return {
        "answer": answer,
        "products": products,
        "report": _shopping_report(
            name=body.title or str(dossier.get("name") or ""),
            url=str(body.url),
            dossier=dossier,
            outside=body.outside or {},
            notes=body.notes or [],
            products=products,
            page_text=body.page_text,
        ),
    }


def _store_list(stores: list[str]) -> str:
    if len(stores) < 2:
        return stores[0] if stores else ""
    if len(stores) == 2:
        return f"{stores[0]} and {stores[1]}"
    return ", ".join(stores[:-1]) + ", and " + stores[-1]


@app.get("/analyze")
async def analyze(Text: str):
    return {"message": "todo"}
