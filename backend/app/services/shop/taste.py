"""What the shopper keeps, returns, and uploads, used to rank similar products."""

import re

from backend.app.services.catalog.identity import known_kind

_COLORS = (
    "navy",
    "black",
    "white",
    "blue",
    "red",
    "green",
    "gray",
    "grey",
    "brown",
    "beige",
    "pink",
    "purple",
    "olive",
    "cream",
    "tan",
    "gold",
    "orange",
    "yellow",
)
_SKIP = {
    "the",
    "and",
    "for",
    "with",
    "mens",
    "men",
    "womens",
    "women",
    "size",
    "new",
    "pack",
    "set",
    "returned",
    "refunded",
    "refund",
}


def describe(name: str, text: str = "") -> dict:
    """Pull a brand, color, and product type out of a title or receipt line."""
    blob = f"{name} {text}".lower()
    color = next((word for word in _COLORS if re.search(rf"\b{word}\b", blob)), "")
    kind = known_kind(name) or known_kind(text)
    brand = ""
    for token in re.findall(r"[A-Za-z0-9&]+", name):
        lowered = token.lower()
        if lowered in _SKIP or lowered in _COLORS or (kind and lowered in kind.split()) or len(lowered) < 3:
            continue
        brand = token
        break
    returned = bool(re.search(r"\b(returned|refunded|refund)\b", blob))
    return {"brand": brand, "color": color, "kind": kind, "returned": returned}


def profile_from(orders: list[dict], receipts: list[dict] | None = None) -> dict:
    """Brands and colors the shopper kept, and brands they sent back."""
    brands: dict[str, int] = {}
    colors: dict[str, int] = {}
    avoid: dict[str, int] = {}
    rows = list(orders or [])
    for receipt in receipts or []:
        rows.extend(receipt.get("items") or [])
    for row in rows:
        name = str(row.get("name") or row.get("product_name") or "")
        extra = str(row.get("materials") or row.get("text") or "")
        facts = describe(name, extra)
        brand = str(row.get("brand") or facts["brand"])
        color = str(row.get("color") or facts["color"])
        returned = bool(row.get("returned")) or facts["returned"] or "returned:yes" in extra.lower()
        status = str(row.get("status") or row.get("delivery_status") or "")
        if status.lower() == "returned":
            returned = True
        if returned and brand:
            avoid[brand] = avoid.get(brand, 0) + 1
            continue
        if brand:
            brands[brand] = brands.get(brand, 0) + 1
        if color:
            colors[color] = colors.get(color, 0) + 1
    return {
        "brands": _top(brands),
        "colors": _top(colors),
        "avoid": _top(avoid),
    }


def load_taste(user_id: str = "shopper") -> dict:
    """Read this shopper's saved orders and uploaded receipts."""
    from backend.app.services.shop.cart import contact

    try:
        orders = contact().past_orders(user_id)
    except KeyError:
        orders = []
    rows = [
        {
            "name": order.product_name,
            "materials": order.materials,
            "status": order.delivery_status,
        }
        for order in orders
    ]
    from backend.app.services.shop.receipts import saved_receipts

    return profile_from(rows, saved_receipts(user_id))


def personalize(products: list[dict], taste: dict | None = None) -> list[dict]:
    """Rank the same kind of product toward brands and colors the shopper kept."""
    taste = taste or {"brands": [], "colors": [], "avoid": []}
    brands = [item.lower() for item in taste.get("brands") or []]
    colors = [item.lower() for item in taste.get("colors") or []]
    avoid = [item.lower() for item in taste.get("avoid") or []]

    def score(product: dict) -> int:
        name = str(product.get("name") or "").lower()
        value = 0
        if any(brand in name for brand in avoid):
            value -= 5
        if any(brand in name for brand in brands):
            value += 3
        if any(color in name for color in colors):
            value += 2
        score = product.get("reviewScore")
        if isinstance(score, (int, float)):
            value += int(score)
        low = product.get("footprintLow")
        if isinstance(low, int):
            value += 3 if low <= 30 else 1 if low <= 100 else 0
        return value

    ranked = sorted(products, key=score, reverse=True)
    kept = []
    for product in ranked:
        if score(product) <= -5:
            continue
        because = _because(str(product.get("name") or ""), brands, colors, product)
        kept.append({**product, "because": because})
    return kept


def _because(name: str, brands: list[str], colors: list[str], product: dict | None = None) -> str:
    lowered = name.lower()
    brand = next((item for item in brands if item in lowered), "")
    color = next((item for item in colors if item in lowered), "")
    product = product or {}
    if brand and color:
        line = f"Close to {color}, from {brand}, which you have kept."
    elif brand:
        line = f"From {brand}, a brand you have kept."
    elif color:
        line = f"Close to {color}, a color you have kept."
    else:
        line = "Same kind of product as the one on this page."
    score = product.get("reviewScore")
    low, high = product.get("footprintLow"), product.get("footprintHigh")
    if isinstance(score, (int, float)):
        line += f" Reviews average {score} out of 5."
    if isinstance(low, int) and isinstance(high, int):
        line += f" About {low}–{high} kg CO2e."
    return line


def _top(counts: dict[str, int]) -> list[str]:
    return [name for name, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[:4]]
