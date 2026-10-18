"""Products the shopper saves from the agent's recommendations."""

from datetime import datetime, timezone

_items: dict[str, list[dict]] = {}


def add_wishlist(item: dict, user_id: str = "shopper") -> dict:
    """Save one recommended product and text the shopper on Photon 2.0."""
    from backend.app.integrations.photon_line import send_intro
    from backend.app.integrations.supabase_store import save_wishlist
    url = str(item.get("url") or "").strip()
    name = " ".join(str(item.get("name") or "").split())
    if not url or not name:
        return {"saved": False, "answer": "That product needs a name and a link before it can be saved."}
    saved = {
        "url": url,
        "name": name[:160],
        "store": str(item.get("store") or ""),
        "price": str(item.get("price") or ""),
        "imageUrl": str(item.get("imageUrl") or item.get("image_url") or ""),
        "environmentScore": item.get("environmentScore"),
        "savedAt": datetime.now(timezone.utc).isoformat(),
    }
    rows = _items.setdefault(user_id, [])
    rows[:] = [row for row in rows if row["url"] != url]
    rows.insert(0, saved)
    save_wishlist(saved, user_id)
    price = f" for ${saved['price']}" if saved["price"] else ""
    text = f"Saved {saved['name']} from {saved['store'] or 'a store'}{price} to your wishlist. {url}"
    result = send_intro(text) or {}
    if result.get("sent"):
        answer = f"{saved['name']} is on your wishlist. A text was sent."
    else:
        reason = str(result.get("reason") or "The Photon text was not delivered.")
        answer = f"{saved['name']} is on your wishlist. {reason}"
    return {"saved": True, "answer": answer, "item": _public(saved), "text": result}


def wishlist(user_id: str = "shopper") -> dict:
    """Return the products this shopper saved, including ones stored in Supabase."""
    from backend.app.integrations.supabase_store import load_wishlist

    stored = load_wishlist(user_id)
    by_url = {row["url"]: row for row in _items.get(user_id, [])}
    for row in stored or []:
        by_url[row["url"]] = row
    rows = sorted(by_url.values(), key=lambda row: row.get("savedAt") or "", reverse=True)
    return {"items": [_public(row) for row in rows]}


def _public(row: dict) -> dict:
    return {
        "url": row.get("url") or "",
        "name": row.get("name") or "",
        "store": row.get("store") or "",
        "price": row.get("price") or "",
        "imageUrl": row.get("imageUrl") or "",
        "environmentScore": row.get("environmentScore"),
        "savedAt": row.get("savedAt") or "",
    }
