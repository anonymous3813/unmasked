"""Activity the shopping agent has already recorded."""

from datetime import datetime, timezone

_KINDS = ("page", "ask", "message", "call", "order", "intro")
_entries: list[dict] = []


def reset() -> None:
    """Clear page, question, and text entries. Profile rows stay on the profile."""
    _entries.clear()


def record(kind: str, title: str, detail: str = "", url: str = "") -> dict:
    """Append one agent action that is not already stored on the shopper profile."""
    entry = {
        "id": f"R{len(_entries) + 1:04d}",
        "kind": kind if kind in _KINDS else "page",
        "title": _clip(title, 160) or "Agent activity",
        "detail": _clip(detail, 280),
        "url": _clip(url, 300),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    from backend.app.services.registry.vote import deliberate

    entry["ballot"] = deliberate(entry, _entries[-1] if _entries else None)
    if not entry["ballot"].get("admitted"):
        return entry
    _entries.append(entry)
    del _entries[:-200]
    from backend.app.integrations.supabase_store import save_entry

    save_entry(entry)
    return entry


def snapshot() -> dict:
    """Return the newest agent actions, including messages, calls, and orders."""
    from backend.app.integrations.supabase_store import load_entries

    stored = load_entries()
    by_id = {entry["id"]: entry for entry in _entries}
    for entry in stored or []:
        current = by_id.get(entry["id"])
        if current and current.get("ballot"):
            continue
        by_id[entry["id"]] = entry
    entries = [*by_id.values(), *_profile_entries()]
    entries.sort(key=lambda item: item["at"], reverse=True)
    counts = {kind: 0 for kind in _KINDS}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return {"entries": entries[:200], "counts": counts}


def _profile_entries() -> list[dict]:
    from backend.app.services.shop.cart import contact

    try:
        profile = contact().profile("shopper")
    except KeyError:
        return []
    rows = []
    for message in profile.messages:
        speaker = "You" if message.role.value == "user" else "Your Online Assistant"
        rows.append(_row("message", speaker, message.body, message.created_at))
    for call in profile.calls:
        rows.append(_row("call", "Call", call.summary, call.created_at))
    for order in profile.orders:
        price = f"${order.price}" if order.price and not str(order.price).startswith("$") else order.price
        parts = [part for part in (order.store, price, order.order_id) if part]
        rows.append(_row("order", order.product_name, " · ".join(parts), order.ordered_at, str(order.product_url)))
    return rows


def _row(kind: str, title: str, detail: str, at: datetime, url: str = "") -> dict:
    return {
        "id": f"{kind}-{at.timestamp():.0f}-{abs(hash(detail)) % 100000}",
        "kind": kind,
        "title": _clip(title, 160) or "Agent activity",
        "detail": _clip(detail, 280),
        "url": url,
        "at": at.isoformat(),
    }


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
