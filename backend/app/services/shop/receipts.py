"""Receipts the shopper uploads, read for the product, brand, and color."""

import re

_receipts: dict[str, list[dict]] = {}
_MONEY = re.compile(r"[£$€]\s*(-?\d+(?:\.\d{2})?)")
_PRODUCT_WORD = re.compile(r"\b(jacket|shoe|shirt|laptop|mower|head|dress|coat)\b", re.I)
_SKIP = re.compile(
    r"\b(shipping|delivery|postage|promotion|promotions|discount|vat|tax|subtotal|total|invoice|asin|qty|quantity|fee|fees|paid|address|support|description|information)\b",
    re.I,
)


def reset() -> None:
    _receipts.clear()


def saved_receipts(user_id: str = "shopper") -> list[dict]:
    return [dict(item) for item in _receipts.get(user_id, [])]


def add_receipt(text: str, filename: str = "", user_id: str = "shopper") -> dict:
    """Store one receipt and the products read from it for this shopper."""
    items = read_receipt(text)
    record = {
        "filename": filename or "Receipt",
        "text": " ".join(str(text or "").split())[:500],
        "items": items,
        "userId": user_id,
    }
    rows = _receipts.setdefault(user_id, [])
    rows.append(record)
    del rows[:-40]
    from backend.app.integrations.supabase_store import save_receipt

    save_receipt(record)
    return record


def remember_receipts(records: list[dict]) -> None:
    """Load bills that were saved before this process started."""
    for record in records:
        user_id = str(record.get("userId") or record.get("user_id") or "shopper")
        rows = _receipts.setdefault(user_id, [])
        if len(rows) >= 40:
            continue
        rows.append(record)


def read_receipt(text: str) -> list[dict]:
    """Read product lines from receipt text. A return line is kept out of the brands they like."""
    from backend.app.services.shop.taste import describe

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    items = []
    store = lines[0][:80] if lines else ""
    pending: tuple[str, str] | None = None
    prices: list[str] = []

    def flush() -> None:
        nonlocal pending, prices
        if pending and len(items) < 12:
            name, original = pending
            name = re.sub(r"\s+returned$", "", name, flags=re.I).strip(" -|,")
            if prices or _PRODUCT_WORD.search(name):
                facts = describe(original)
                items.append(
                    {
                        "name": name[:140],
                        "brand": facts["brand"],
                        "color": facts["color"],
                        "kind": facts["kind"],
                        "price": next((price for price in reversed(prices) if not price.startswith("-")), ""),
                        "store": store,
                        "returned": facts["returned"],
                    }
                )
        pending = None
        prices = []

    for line in lines:
        if _SKIP.search(line):
            flush()
            continue
        found = [price for price in _MONEY.findall(line)]
        name = _MONEY.sub("", line).strip(" -|,")
        if _named_product(name):
            flush()
            pending = (name, line)
            prices = found
            continue
        if found and pending:
            prices.extend(found)
    flush()
    return items


def _named_product(name: str) -> bool:
    return len(name) >= 4 and bool(re.search(r"[A-Za-z]{3,}", name))


def read_upload(filename: str, data: bytes) -> str:
    """Read a bill file. A photo is sent to the vision reader."""
    extracted = text_from_upload(filename, data)
    mime = _image_mime(filename)
    if data and mime and not " ".join(extracted.split()):
        from backend.app.integrations.openai_client import OpenAIClient

        try:
            return OpenAIClient().read_image(data, mime)
        except RuntimeError:
            return ""
    return extracted


def _image_mime(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    return ""


def text_from_upload(filename: str, data: bytes) -> str:
    """Pull text from a pasted file. Images are left for the caller to describe."""
    name = (filename or "").lower()
    if name.endswith((".txt", ".csv", ".html", ".htm")) or not name.endswith(".pdf"):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            if not name.endswith(".pdf"):
                return ""
    parts = re.findall(rb"\((?:\\\)|[^)\n]){4,160}\)", data)
    decoded = []
    for part in parts[:80]:
        try:
            decoded.append(part[1:-1].decode("latin-1"))
        except UnicodeDecodeError:
            continue
    if decoded:
        return "\n".join(decoded)
    plain = re.findall(rb"[\x20-\x7e]{8,}", data)
    return "\n".join(piece.decode("ascii") for piece in plain[:60])
