"""Seeded shopping report for the Unmasked demo.

Every fact in this module is a fixture. It is not a live store, review site,
or certification registry.
"""

PRODUCT_NAME = "Harbor Headphones"
PRODUCT_URL = "https://demo.unmasked.local/products/harbor-headphones"

_MONITORS: dict[str, dict] = {}


def demo_report() -> dict:
    """Return the full headphones report used by the dashboard and extension."""
    return {
        "simulated": True,
        "label": "Demo data. Quotations, review counts, and prices are fixtures, not a live store.",
        "product": {
            "name": PRODUCT_NAME,
            "brand": "Northwind Audio",
            "seller": "Northwind Audio",
            "price": "89.00",
            "currency": "USD",
            "url": PRODUCT_URL,
            "category": "Headphones",
        },
        "assessment": "The return window is short, and the cushion complaint matches a return already on this demo profile.",
        "coverage": "Fixture policy, one marketing claim, four fixture reviews, and no certification record.",
        "memory": {
            "product": "North Loop Headphones",
            "returnedAt": "2026-03-02",
            "reason": "the ear cushions deteriorated after two months.",
            "authorized": True,
        },
        "concerns": [
            {
                "severity": "high",
                "category": "Return window",
                "evidenceLevel": "verified",
                "explanation": "The fixture policy allows 14 days and makes the buyer pay return shipping.",
                "quotation": "Items may be returned within 14 days. The buyer pays return shipping.",
                "source": "https://demo.unmasked.local/policies/returns",
                "action": "Decide within 14 days, and expect to pay the return shipment.",
            },
            {
                "severity": "high",
                "category": "Warranty exclusion",
                "evidenceLevel": "verified",
                "explanation": "Cushion wear is excluded from the fixture warranty.",
                "quotation": "The warranty excludes damage from normal wear, including ear cushions.",
                "source": "https://demo.unmasked.local/policies/warranty",
                "action": "Do not rely on the warranty if the cushions flatten.",
            },
        ],
        "claim": {
            "text": "Battery lasts 30 hours.",
            "verdict": "insufficient evidence",
            "evidenceLevel": "unknown",
            "explanation": "The fixture has the seller's sentence and no independent test.",
            "quotation": "The battery lasts 30 hours on a single charge.",
            "source": PRODUCT_URL,
        },
        "review": {
            "category": "Cushion durability",
            "evidenceLevel": "reported",
            "reports": 4,
            "excerpt": "The ear cushions flattened before the second month.",
            "source": "https://demo.unmasked.local/reviews/harbor-headphones",
            "limitation": "Four fixture reviews describe this. That does not prove the failure rate.",
        },
        "environment": {
            "evidenceLevel": "unknown",
            "finding": "The seller says the mailer is recycled paper. No certification record is in this demo.",
            "quotation": "Ships in recycled paper packaging.",
            "source": PRODUCT_URL,
            "score": 46,
        },
        "value": {
            "price": "89.00",
            "evidenceLevel": "inferred",
            "finding": "The $89 price is a fixture. No tested lifespan is on file, so there is no total cost of ownership.",
        },
        "alternatives": [
            {
                "name": "Lumen Repairable Headphones",
                "store": "Demo Catalog",
                "price": "110.00",
                "url": "https://demo.unmasked.local/products/lumen-repairable",
                "why": "Replaceable cushions and a 30-day return the seller pays for.",
                "addresses": "The cushion failure you returned before, and Harbor's short return window.",
                "tradeoff": "The fixture price is $21 higher. No independent durability test is included.",
                "recommended": True,
            },
            {
                "name": "Cedar Studio Headphones",
                "store": "Demo Catalog",
                "price": "140.00",
                "url": "https://demo.unmasked.local/products/cedar-studio",
                "why": "A two-year fixture warranty that names cushion replacement.",
                "addresses": "Warranty coverage Harbor excludes.",
                "tradeoff": "Heavier, and the fixture price is $140.",
                "recommended": False,
            },
            {
                "name": "Plain Loop Headphones",
                "store": "Demo Catalog",
                "price": "64.00",
                "url": "https://demo.unmasked.local/products/plain-loop",
                "why": "Lower fixture price.",
                "addresses": "Budget only.",
                "tradeoff": "The same fixture reviews mention cushion flattening.",
                "recommended": False,
            },
        ],
    }


def demo_answer(question: str) -> str:
    """Answer a demo question from the fixture only."""
    from backend.app.services.shop.guard import UNSOURCED, gate, sanitize

    blocked = gate(question)
    if blocked is not None:
        return blocked
    return sanitize(_fixture_answer(question, UNSOURCED))


def _fixture_answer(question: str, unsourced: str) -> str:
    report = demo_report()
    text = (question or "").lower()
    memory = report["memory"]
    recommended = next(item for item in report["alternatives"] if item["recommended"])
    if any(word in text for word in ("return", "returned", "before", "recommend")):
        return (
            f"You returned {memory['product']} on {memory['returnedAt']} because {memory['reason']} "
            f"{PRODUCT_NAME} have a similar reported cushion problem, and the warranty excludes cushion wear. "
            f"{recommended['name']} are the better fit in this demo: {recommended['why']} "
            "That does not mean they are problem-free. Prices and reviews here are demo fixtures."
        )
    if "environment" in text or "green" in text or "sustain" in text:
        return report["environment"]["finding"] + " This is demo data."
    if "wrong" in text or "concern" in text or "risk" in text:
        first, second = report["concerns"]
        return f"{first['explanation']} {second['explanation']} This is demo data."
    if "complain" in text or "review" in text:
        review = report["review"]
        return f"{review['reports']} fixture reviews say: {review['excerpt']} {review['limitation']}"
    if "claim" in text or "battery" in text:
        claim = report["claim"]
        return f"The claim \"{claim['text']}\" is {claim['verdict']}. {claim['explanation']}"
    shopping = (
        "return",
        "recommend",
        "environment",
        "green",
        "sustain",
        "wrong",
        "concern",
        "risk",
        "complain",
        "review",
        "claim",
        "battery",
        "headphone",
        "harbor",
        "price",
        "warrant",
        "cushion",
        "policy",
    )
    if not any(word in text for word in shopping):
        return unsourced
    return (
        f"{report['assessment']} Ask about the return, the battery claim, the reviews, "
        "or which model fits what you returned before. This is demo data."
    )


def watch_policy(product: str = PRODUCT_NAME) -> dict:
    """Record one opted-in return-policy monitor for the demo product."""
    key = (product or PRODUCT_NAME).strip() or PRODUCT_NAME
    existing = _MONITORS.get(key)
    if existing is not None:
        return existing
    record = {
        "id": f"M{len(_MONITORS) + 1:03d}",
        "product": key,
        "kind": "return_policy",
        "status": "opted_in",
        "simulated": True,
        "message": (
            f"Monitoring is on for {key} return-policy changes. "
            "This demo does not send a Photon message, and no policy change was detected."
        ),
    }
    _MONITORS[key] = record
    return record


def reset_monitors() -> None:
    """Clear demo monitors between tests."""
    _MONITORS.clear()
