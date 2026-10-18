import io
import os
import re
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from backend.app.demo.report import demo_answer, demo_report, watch_policy

from backend.app.services.registry.log import for_product, record, snapshot
from backend.app.services.catalog.page import accepts_page
from backend.app.services.shop.products import find_products, paired_item
from backend.app.services.shop.tax import tax_note
from backend.app.services.shop.agent import answer_question
from backend.app.integrations.photon_line import send_intro
from backend.app.services.shop.accounts import login, logout, register, require_user
from backend.app.services.shop.cart import assistant, mark_returned, orders_answer, purchase, refresh_delivery
from backend.app.services.shop.wishlist import add_wishlist, wishlist
from backend.app.services.shop.inbox import inbox, place_call, send_message
from backend.app.services.shop.marks import offer_alternatives, page_report
from backend.app.integrations.openai_client import OpenAIClient
from backend.app.services.catalog.report import build_report, look_at_page
from backend.app.services.claim_detection_service import ClaimDetectionService

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


class AuthRequest(BaseModel):
    email: str = ""
    password: str = ""
    name: str = ""
    phone: str = ""


class ReturnRequest(BaseModel):
    order_id: str = ""


class ReceiptRequest(BaseModel):
    text: str = ""
    filename: str = ""
    data_base64: str = ""


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


SITE = ROOT / "registry-site" / "dist"


@app.get("/logo.jpeg")
def logo():
    """Serve the Unmasked mark from assets/logo.jpeg."""
    return FileResponse(ROOT / "assets" / "logo.jpeg", media_type="image/jpeg")


@app.get("/")
def home():
    """Serve the React account and registry app."""
    page = SITE / "index.html"
    if not page.is_file():
        page = ROOT / "registry-site" / "index.html"
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


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


@app.post("/auth/register")
def register_account(body: AuthRequest):
    """Create an account for this shopper's orders, wishlist, and taste."""
    return _with_update(register(body.email, body.password, body.name, body.phone))


@app.post("/auth/login")
def login_account(body: AuthRequest):
    """Return a session for an existing account, plus a product update from what they already bought."""
    return _with_update(login(body.email, body.password, body.phone))


def _receive_sms(payload: dict) -> dict:
    from backend.app.integrations.photon_line import send_to_space
    from backend.app.services.shop.updates import sms_reply

    message = _incoming_message(payload)
    text, picture = _read_content(message.get("content"))
    space = message.get("space") if isinstance(message.get("space"), dict) else {}
    space_id = str(space.get("id") or message.get("spaceId") or "")
    sender = message.get("sentBy") if isinstance(message.get("sentBy"), dict) else {}
    agent = message.get("receivedBy") if isinstance(message.get("receivedBy"), dict) else {}
    phone = str(sender.get("handle") or "")
    agent_id = str(agent.get("id") or "")
    if sender.get("kind") == "agent":
        return {"ignored": True}
    answer = sms_reply(text, phone, picture)
    if space_id.startswith("pho_spc_"):
        sent = send_to_space(space_id, answer, agent_id)
    else:
        sent = send_intro(answer, phone)
    return {"answer": answer, "sent": bool(sent.get("sent")), "reason": sent.get("reason") or ""}


def _incoming_message(payload: dict) -> dict:
    """Photon wraps a received SMS as data.object."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    message = data.get("object") if isinstance(data.get("object"), dict) else data
    if isinstance(message.get("message"), dict):
        message = message["message"]
    return message if isinstance(message, dict) else {}


def _read_content(content: dict) -> tuple[str, bool]:
    """Read a text, a photo, or a text-and-photo group."""
    if not isinstance(content, dict):
        return "", False
    kind = str(content.get("type") or "")
    if kind == "group":
        texts = []
        picture = False
        for part in content.get("parts") or []:
            text, has_picture = _read_content(part if isinstance(part, dict) else {})
            if text:
                texts.append(text)
            picture = picture or has_picture
        return " ".join(texts), picture
    picture = kind == "attachment" or kind in {"image", "media"} or bool(content.get("attachmentId"))
    return str(content.get("text") or ""), picture


def _with_update(session: dict) -> dict:
    """Attach the purchase update and try to text it once the shopper is signed in."""
    from backend.app.services.shop.updates import deliver_update

    account = session.get("account") or {}
    session["update"] = deliver_update(
        str(account.get("id") or ""),
        str(account.get("name") or ""),
        str(account.get("phone") or ""),
    )
    return session


@app.post("/photon/sms")
async def photon_sms(request: Request):
    """Reply when the shopper texts or sends a picture to the Unmasked number."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return _receive_sms(payload if isinstance(payload, dict) else {})


@app.post("/auth/logout")
def logout_account(authorization: str | None = Header(default=None)):
    """Forget the session used by the website or the extension."""
    return logout(authorization)


@app.post("/page-notes")
def page_notes(body: PageNotesRequest, authorization: str | None = Header(default=None)):
    require_user(authorization)
    """Return the price, policy, and product marks for one product page."""
    try:
        report = page_report(
            str(body.url),
            body.listed_price,
            body.postal_code,
            body.page_text,
            body.record,
            body.product_page,
        )
    except Exception:
        report = {
            "notes": [],
            "visits": [],
            "dossier": {},
            "outside": {"reviews": [], "policies": [], "environment": []},
            "brief": "",
            "footprint": {},
            "active": True,
        }
    titles = [
        str(note.get("title") or note.get("kind") or "")
        for note in report.get("notes") or []
    ]
    titles = [title for title in titles if title]
    report["registry"] = for_product(str(body.url), str((body.record or {}).get("name") or ""))
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
def sales_tax(body: TaxRequest, authorization: str | None = Header(default=None)):
    """Return the location tax mark for one listed price."""
    require_user(authorization)
    note = tax_note(body.amount, body.postal_code)
    return {"note": note}


@app.post("/intro")
def intro(body: IntroRequest, authorization: str | None = Header(default=None)):
    """Send the first product summary by text, including when the page had no policy changes."""
    require_user(authorization)
    result = send_intro(body.text)
    detail = "Delivered." if result.get("sent") else str(result.get("reason") or "Not delivered.")
    record("intro", "First text", detail)
    return result


@app.get("/assistant")
def assistant_profile(authorization: str | None = Header(default=None)):
    """Return the name and phone number shown in the chat."""
    require_user(authorization)
    return assistant()


@app.post("/ask")
def ask(body: AskRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    """Answer one product question with the shopper's agent."""
    from backend.app.services.shop.guard import gate

    question = body.question.strip()
    blocked = gate(question)
    if blocked is not None:
        return _asked(body, blocked, [])
    if not accepts_page(str(body.url), body.product_page):
        answer = "I only read product pages. Open a product and ask me there."
        return _asked(body, answer, [])
    hunt = paired_item(question, body.title or "")
    if hunt:
        kind, prefix = hunt
        products = find_products(kind, body.title or "", body.page_text, str(body.url), query_prefix=prefix)
        if not products and prefix:
            products = find_products(kind, body.title or "", body.page_text, str(body.url))
        if products:
            stores = _store_list(list(dict.fromkeys(product["store"] for product in products)))
            lead = f"These {kind}s go with this product" if prefix else f"These {kind} listings are from {stores}"
            answer = (
                f"{lead}. The search preferred eco-friendly listings, and they are from {stores}."
                if prefix
                else f"These {kind} listings are from {stores}. Add any of them to your cart."
            )
        else:
            looked = f"eco-friendly {kind}s" if prefix else f"{kind}s"
            answer = f"I looked for {looked} that go with this product and did not get a store listing back."
        record("ask", question, answer, str(body.url))
        return _asked(body, answer, products)
    remembered = orders_answer(question, user_id=user["id"])
    if remembered is not None:
        return _asked(body, remembered, [])
    researched = _research_reply(question, body.title or "", str(body.url), body.page_text, user["id"])
    if researched is not None:
        answer, products = researched
        record("ask", question, answer, str(body.url))
        return _asked(body, answer, products)
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
        products = offer_alternatives(body.title or "", str(body.url), body.page_text, user_id=user["id"]).get("products") or []
    record("ask", question, answer, str(body.url))
    return _asked(body, answer, products)


@app.get("/inbox")
def read_inbox(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    """Return this shopper's messages, calls, and orders."""
    return inbox(user_id=user["id"])


@app.post("/inbox/message")
def inbox_message(body: InboxMessage, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    """Message the assistant about the cart, orders, or this product."""
    return send_message(body.text, body.cart, notes=body.notes, user_id=user["id"])


@app.post("/inbox/call")
def inbox_call(body: InboxCall, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    """Call the assistant and hear the cart and orders."""
    return place_call(body.cart, notes=body.notes, user_id=user["id"])


@app.post("/cart/checkout")
def checkout(body: CheckoutRequest, authorization: str | None = Header(default=None)):
    """Record every cart item as an order on this shopper's profile."""
    user = require_user(authorization)
    items = [item.model_dump(mode="json") for item in body.items]
    return purchase(items, user_id=user["id"])


@app.get("/wishlist")
def read_wishlist(authorization: str | None = Header(default=None)):
    """Return products this shopper saved from the agent's recommendations."""
    user = require_user(authorization)
    return wishlist(user["id"])


@app.post("/wishlist")
def save_wishlist_item(body: WishlistItem, authorization: str | None = Header(default=None)):
    """Save a recommended product for this shopper."""
    user = require_user(authorization)
    return add_wishlist(body.model_dump(), user["id"])


@app.get("/purchases")
def purchases(authorization: str | None = Header(default=None)):
    """Return this shopper's purchases, uploaded receipts, and taste."""
    from backend.app.services.shop.receipts import saved_receipts
    from backend.app.services.shop.taste import load_taste

    user = require_user(authorization)
    from backend.app.services.shop.updates import account_update

    payload = refresh_delivery(user_id=user["id"])
    payload["receipts"] = saved_receipts(user["id"])
    payload["taste"] = load_taste(user["id"])
    payload["update"] = account_update(user["id"], user.get("name") or "")
    return payload


@app.post("/purchases/return")
def return_purchase(body: ReturnRequest, authorization: str | None = Header(default=None)):
    """Mark an order this shopper sent back, so similar products avoid that brand."""
    user = require_user(authorization)
    return mark_returned(body.order_id, user_id=user["id"])


@app.post("/receipts")
def create_receipt(body: ReceiptRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    """Read a past bill and keep the products, brands, and colors on the dashboard."""
    import base64

    from backend.app.services.shop.receipts import add_receipt, read_upload

    raw = body.text
    filename = body.filename or "Receipt"
    if body.data_base64.strip():
        try:
            data = base64.b64decode(body.data_base64)
        except ValueError:
            data = b""
        raw = read_upload(filename, data) or raw
    if not " ".join(raw.split()):
        return {"filename": filename, "items": [], "reason": "No receipt text could be read."}
    return add_receipt(raw, filename, user["id"])


@app.get("/receipts")
def read_receipts(authorization: str | None = Header(default=None)):
    """Return this shopper's bills and the brands and colors kept from them."""
    from backend.app.services.shop.receipts import saved_receipts
    from backend.app.services.shop.taste import load_taste

    user = require_user(authorization)
    return {"receipts": saved_receipts(user["id"]), "taste": load_taste(user["id"])}


@app.post("/alternatives")
def alternatives(body: AlternativesRequest, authorization: str | None = Header(default=None)):
    """Return similar listings ranked with this shopper's kept brands and colors."""
    user = require_user(authorization)
    from backend.app.services.shop.marks import _named_product

    name = _named_product({"heading": body.name, "name": body.name, "candidates": []}, body.page_text)
    found = offer_alternatives(name or body.name, body.url, body.page_text, body.listed_price, user["id"])
    found["registry"] = for_product(body.url, body.name)
    return found


def _shopping_report(**kwargs) -> dict:
    grounded = build_report(**kwargs)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return grounded
    try:
        return look_at_page(grounded, kwargs.get("page_text") or "", complete=OpenAIClient().complete)
    except Exception:
        return grounded


def _research_reply(question: str, title: str, url: str, page_text: str, user_id: str) -> tuple[str, list] | None:
    """Search outside the open page when the question needs reviews, carbon, policies, or other brands."""
    asked = question.lower()
    lines = []
    products: list = []
    if re.search(r"\b(?:reviews?|complain\w*|ratings?|customers?)\b", asked):
        from backend.app.services.catalog.dossier import outside_evidence

        outside = outside_evidence(title)
        quotes = [str(item.get("quote") or "").strip() for item in outside.get("reviews") or [] if str(item.get("quote") or "").strip()]
        lines.append(" ".join(quotes[:2]) if quotes else str((outside.get("coverage") or {}).get("reviews") or ""))
    if re.search(r"\b(?:carbon|footprint|co2|environment\w*|materials?)\b", asked):
        from backend.app.services.shop.marks import _footprint

        footprint = _footprint(title, page_text, {}, url)
        lines.append(str(footprint.get("coverage") or footprint.get("headline") or ""))
    if re.search(r"\b(?:return|refund|warrant\w*|polic\w*)\b", asked):
        from backend.app.services.catalog.dossier import outside_evidence

        outside = outside_evidence(title)
        policies = [str(item.get("text") or "").strip() for item in outside.get("policies") or [] if str(item.get("text") or "").strip()]
        lines.append(" ".join(policies[:2]) if policies else str((outside.get("coverage") or {}).get("policies") or ""))
    if re.search(r"\b(?:alternative|alternatives|better|cheaper|other brand|another brand|instead)\b", asked):
        found = offer_alternatives(title, url, page_text, user_id=user_id)
        products = found.get("products") or []
        if products:
            stores = _store_list(list(dict.fromkeys(str(item.get("store") or "") for item in products if item.get("store"))))
            lines.append(f"Other brands and stores listing this kind of product: {stores}.")
        else:
            lines.append(str(found.get("coverage") or "No competing listing was retrieved."))
    lines = [line for line in lines if line.strip()]
    if not lines:
        return None
    return " ".join(lines), products


def _public_answer(answer: str) -> str:
    from backend.app.services.shop.guard import sanitize

    return sanitize(answer)


def _asked(body: AskRequest, answer: str, products: list) -> dict:
    dossier = body.dossier or {}
    return {
        "answer": _public_answer(answer),
        "products": products,
        "registry": for_product(str(body.url), body.title or str((body.dossier or {}).get("name") or "")),
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


def _legal_page(title: str, body: str) -> HTMLResponse:
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Unmasked</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body {{ margin: 0; background: #f7f4ee; color: #1b1f1d; font: 18px/1.5 "Source Sans 3", sans-serif; }}
    header {{ background: #0f3d2a; color: #fff; padding: 16px 24px; }}
    header a {{ color: #fff; font: 700 22px/1 Merriweather, Georgia, serif; text-decoration: none; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 32px 24px 64px; }}
    h1 {{ font-family: Merriweather, Georgia, serif; font-size: 40px; line-height: 1.15; }}
    a {{ color: #21613d; }}
  </style>
</head>
<body>
  <header><a href="/">Unmasked</a></header>
  <main>
    <h1>{title}</h1>
    {body}
    <p><a href="/privacy">Privacy policy</a> · <a href="/terms">Terms</a></p>
  </main>
</body>
</html>"""
    return HTMLResponse(page)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Public privacy policy for the Unmasked text program."""
    return _legal_page(
        "Privacy policy",
        """
        <p>Unmasked texts you only after you enter your mobile number on the Unmasked extension or website and submit the form.</p>
        <p>We collect the mobile number you enter, the words and photos you send to Unmasked, and the email, name, orders, bills, and wishlist on your account.</p>
        <p>We use that information to send the welcome text, to reply when you text us, and to send order and product updates for that account.</p>
        <p>Mobile numbers and text-message consent are not sold and are not shared with third parties for their own marketing. A messaging provider delivers the texts for Unmasked.</p>
        <p>Text STOP to end messages. Text HELP for help.</p>
        <p>This policy was updated on October 18, 2026.</p>
        """,
    )


@app.get("/terms", response_class=HTMLResponse)
def terms():
    """Public terms for the Unmasked text program."""
    return _legal_page(
        "Terms",
        """
        <p>The Unmasked text program sends a welcome message when you sign in with your mobile number, replies when you text or send a photo, and sends order and product updates for that account.</p>
        <p>You opt in by entering your mobile number on the Unmasked extension or website and submitting the form. Consent is not a condition of any purchase.</p>
        <p>Message frequency varies. Message and data rates may apply.</p>
        <p>Reply STOP to cancel. You will receive one confirmation, and then no further program texts. Reply HELP for help.</p>
        <p>These terms were updated on October 18, 2026.</p>
        """,
    )


@app.get("/analyze")
async def analyze(Text: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    service = ClaimDetectionService
    return { "result" : service.analyze_url(Text) }


_assets = SITE / "assets"
if _assets.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets), name="site-assets")
