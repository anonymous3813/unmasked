"""Build a shopping report from dossier, outside evidence, notes, and pictured products."""

import hashlib
import json
import re
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from backend.app.models.response_blocks import (
    Block,
    Finding,
    MissingEvidence,
    ShoppingReport,
    Source,
    SourceList,
    SummaryCard,
    SustainabilityReport,
    Action,
)

_CO2 = re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\s*(?:of\s+)?co2e?", re.IGNORECASE)
_MATERIAL_WORDS = (
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
)
_CERTIFICATIONS = ("GOTS", "OEKO-TEX", "bluesign", "Fair Trade", "Energy Star", "FSC", "GRS")
_STOP = {"with", "from", "this", "that", "pack", "size", "new", "the", "and", "for"}
_BLOCK_ADAPTER = TypeAdapter(Block)
_ACTION_ADAPTER = TypeAdapter(Action)
_SOURCE_ADAPTER = TypeAdapter(Source)


def build_report(
    *,
    name: str,
    url: str,
    dossier: dict | None = None,
    outside: dict | None = None,
    notes: list | None = None,
    products: list | None = None,
    page_text: str = "",
) -> dict:
    """Return a validated report. Carbon figures are copied from product-specific sources."""
    dossier = dossier or {}
    outside = outside or {}
    product = " ".join(str(name or dossier.get("name") or "").split())
    page_url = str(url or "").strip()
    sources: list[Source] = []
    findings: list[Finding] = []

    def add_source(title: str, source_url: str, excerpt: str, source_class: str, specific: bool) -> str | None:
        clean_url = str(source_url or "").strip()
        if not clean_url.startswith("http"):
            return None
        source_id = f"src-{len(sources) + 1}"
        public = excerpt if specific else _CO2.sub("a carbon footprint", excerpt)
        sources.append(
            Source(
                id=source_id,
                title=(title or _domain(clean_url))[:80],
                url=clean_url,
                domain=_domain(clean_url),
                retrievedAt=None,
                excerpt=" ".join(public.split())[:280],
                sourceClass=source_class,
                productSpecific=specific,
            )
        )
        return source_id

    for spec in (dossier.get("specs") or [])[:4]:
        label = str(spec.get("label") or "")
        value = " ".join(str(spec.get("value") or "").split())
        if not value or label.lower() not in {"material", "fabric"}:
            continue
        source_id = add_source("This page", page_url, f"{label}: {value}", "manufacturer", True)
        if source_id and len(findings) < 3:
            findings.append(Finding(label="Material", value=value[:80], status="manufacturer_claim", sourceIds=[source_id]))

    page_material = _material(page_text)
    if page_material and len(findings) < 3 and all(page_material.lower() not in finding.value.lower() for finding in findings):
        source_id = add_source("This page", page_url, f"Material named on the page: {page_material}", "manufacturer", True)
        if source_id:
            findings.append(Finding(label="Material", value=page_material, status="manufacturer_claim", sourceIds=[source_id]))

    verified_figure = ""
    for row in (outside.get("environment") or [])[:3]:
        text = " ".join(str(row.get("text") or "").split())
        source_url = str(row.get("url") or "")
        specific = _specific(product, text)
        figure = _figure(text) if specific else ""
        source_class = "background"
        if specific and figure and not _same_site(page_url, source_url):
            source_class = "independent_product"
        elif specific and _same_site(page_url, source_url):
            source_class = "manufacturer"
        elif specific:
            source_class = "independent_product"
        source_id = add_source(str(row.get("source") or "Outside source"), source_url, text, source_class, specific)
        if source_id and figure and source_class == "independent_product" and not verified_figure and len(findings) < 3:
            verified_figure = figure
            findings.insert(0, Finding(label="Carbon footprint", value=figure, status="verified", sourceIds=[source_id]))
        elif source_id and specific and len(findings) < 3:
            material = _material(text)
            if material and all(material.lower() not in finding.value.lower() for finding in findings):
                findings.append(
                    Finding(label="Material", value=material, status="verified", sourceIds=[source_id])
                )
        certification = _certification(text) if specific else ""
        if source_id and certification and len(findings) < 3:
            findings.append(
                Finding(
                    label="Certification",
                    value=certification,
                    status="manufacturer_claim" if source_class == "manufacturer" else "verified",
                    sourceIds=[source_id],
                )
            )

    for review in (outside.get("reviews") or [])[:2]:
        quote = " ".join(str(review.get("quote") or "").split())
        add_source(
            str(review.get("source") or "Review"),
            str(review.get("url") or ""),
            quote,
            "customer_review",
            _specific(product, quote),
        )

    pictured = _pictured(products or [], notes or [])
    materials = [finding for finding in findings if finding.label == "Material"]
    if verified_figure:
        verdict = f"An outside source states a carbon footprint of {verified_figure}."
        why = "That figure is copied from the source that measured this product."
        status = "verified"
    elif materials:
        verdict = "Material information is available, but product-level emissions are unverified."
        why = "Material information alone is insufficient to calculate a defensible footprint."
        status = "insufficient_evidence"
    else:
        verdict = "Carbon footprint not verified."
        why = "No verified product-specific CO2e measurement was found."
        status = "insufficient_evidence"

    blocks: list[Block] = [
        SummaryCard(verdict=verdict, why=why),
        SustainabilityReport(title="Environmental analysis", status=status, findings=findings[:3]),
    ]
    if not verified_figure:
        blocks.append(
            MissingEvidence(
                metric="product_carbon_footprint",
                reason=(
                    "Carbon footprint not verified. No verified product-specific CO2e measurement was found. "
                    "Material information alone is insufficient to calculate a defensible footprint."
                ),
            )
        )
    if sources:
        blocks.append(SourceList(sourceIds=[source.id for source in sources]))

    actions: list[Action] = []
    if product and page_url.startswith("http"):
        actions.append(_ACTION_ADAPTER.validate_python({"type": "save_product", "label": "Save product", "url": page_url}))
    if pictured:
        actions.append(_ACTION_ADAPTER.validate_python({"type": "compare_alternatives", "label": "Compare greener alternatives"}))
    for source in sources[:2]:
        actions.append(
            _ACTION_ADAPTER.validate_python({"type": "open_source", "label": f"View {source.domain}", "url": source.url})
        )

    follow_ups = []
    if materials:
        follow_ups.append("What are the materials?")
    if any(source.source_class == "customer_review" for source in sources):
        follow_ups.append("What do outside reviews say?")
    if pictured:
        follow_ups.append("Is there a greener option?")

    report = ShoppingReport(
        responseId=hashlib.sha256(f"{page_url}|{product}".encode()).hexdigest()[:12],
        summary=verdict,
        demo=False,
        blocks=blocks,
        sources=sources,
        suggestedActions=actions,
        followUps=follow_ups[:3],
    )
    return report.model_dump(by_alias=True, mode="json")


def look_at_page(report: dict, page_text: str = "", complete=None) -> dict:
    """Ask the agent to phrase the verdict from the open page. Invented carbon figures are dropped."""
    text = " ".join(str(page_text or "").split())
    if complete is None or len(text) < 20:
        return report
    prompt = (
        "You are looking at the product page the shopper has open. "
        "Write the verdict from that page and the retrieved report. "
        "Use only facts that appear in the page or the report. "
        "Do not invent a carbon number, a price, a score, or a certification. "
        "If the report says the carbon footprint is not verified, keep that. "
        'Return JSON: {"verdict": "one sentence the shopper should know", "why": "one sentence on why it matters"}\n\n'
        f"Page text:\n{text[:6000]}\n\n"
        f"Report summary:\n{report.get('summary') or ''}\n"
    )
    try:
        raw = complete(prompt)
    except RuntimeError:
        return report
    payload = _json_object(raw)
    verdict = " ".join(str(payload.get("verdict") or "").split())
    why = " ".join(str(payload.get("why") or "").split())
    if not verdict or _invented_figure(f"{verdict} {why}", text, report):
        return report
    blocks = []
    for block in report.get("blocks") or []:
        if isinstance(block, dict) and block.get("type") == "summary_card":
            blocks.append({**block, "verdict": verdict[:280], "why": (why or str(block.get("why") or ""))[:280]})
        else:
            blocks.append(block)
    updated = dict(report)
    updated["blocks"] = blocks
    updated["summary"] = verdict[:280]
    return clean_report(updated)


def clean_report(payload: dict) -> dict:
    """Drop unknown, invalid, or demo blocks before anything renders them."""
    raw = payload if isinstance(payload, dict) else {}
    if raw.get("demo") is not False:
        raw = {
            "responseId": str(raw.get("responseId") or "empty"),
            "summary": "",
            "demo": False,
            "blocks": [],
            "sources": [],
            "suggestedActions": [],
            "followUps": [],
        }
    blocks = []
    for block in raw.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        try:
            blocks.append(_BLOCK_ADAPTER.validate_python(block))
        except ValidationError:
            continue
    sources = []
    for source in raw.get("sources") or []:
        if not isinstance(source, dict):
            continue
        try:
            sources.append(_SOURCE_ADAPTER.validate_python(source))
        except ValidationError:
            continue
    actions = []
    for action in raw.get("suggestedActions") or []:
        if not isinstance(action, dict):
            continue
        try:
            actions.append(_ACTION_ADAPTER.validate_python(action))
        except ValidationError:
            continue
    follow_ups = [str(item) for item in (raw.get("followUps") or []) if str(item).strip()][:3]
    report = ShoppingReport(
        responseId=str(raw.get("responseId") or "empty"),
        summary=str(raw.get("summary") or ""),
        demo=False,
        blocks=blocks,
        sources=sources,
        suggestedActions=actions,
        followUps=follow_ups,
    )
    return report.model_dump(by_alias=True, mode="json")


def _json_object(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _invented_figure(text: str, page_text: str, report: dict) -> bool:
    figure = _figure(text)
    if not figure:
        return False
    corpus = f"{page_text} {json.dumps(report)}".lower()
    return figure.lower() not in corpus


def _figure(text: str) -> str:
    match = _CO2.search(text or "")
    if match is None:
        return ""
    return " ".join(match.group(0).split())


def _specific(name: str, text: str) -> bool:
    from backend.app.services.catalog.identity import mentions_product, search_label

    label = search_label(name)
    return mentions_product(label, text) or mentions_product(name, text)


def _material(text: str) -> str:
    haystack = (text or "").lower()
    for word in _MATERIAL_WORDS:
        if word in haystack:
            return word
    return ""


def _certification(text: str) -> str:
    haystack = text or ""
    for name in _CERTIFICATIONS:
        if name.lower() in haystack.lower():
            return name
    return ""


def _domain(url: str) -> str:
    return urlparse(url).netloc or url


def _same_site(page_url: str, source_url: str) -> bool:
    page = _domain(page_url).removeprefix("www.")
    source = _domain(source_url).removeprefix("www.")
    return bool(page and source and page == source)


def _pictured(products: list, notes: list) -> list[dict]:
    rows = []
    candidates = list(products)
    for note in notes:
        if isinstance(note, dict) and note.get("kind") == "recommendation":
            candidates.append(
                {
                    "name": note.get("productName") or note.get("title") or "",
                    "url": note.get("productUrl") or note.get("url") or "",
                    "imageUrl": note.get("imageUrl") or "",
                }
            )
    for product in candidates:
        if not isinstance(product, dict):
            continue
        image = str(product.get("imageUrl") or "")
        product_url = str(product.get("url") or "")
        if image.startswith("http") and product_url.startswith("http"):
            rows.append(product)
        if len(rows) == 4:
            break
    return rows
