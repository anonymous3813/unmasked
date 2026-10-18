"""Activity the shopping agent has already recorded."""

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

_KINDS = ("page", "ask", "message", "call", "order", "intro")
_PRIVATE_KINDS = {"message", "call", "order", "intro"}
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


def for_product(url: str, name: str = "") -> list[dict]:
    """Return public registry rows for this product page."""
    wanted = _url_key(url)
    label = " ".join(str(name or "").split())
    matched = []
    for entry in _public_entries():
        same_page = bool(wanted) and _url_key(str(entry.get("url") or "")) == wanted
        if same_page or _name_hit(label, entry):
            matched.append(
                {
                    "id": entry.get("id") or "",
                    "kind": entry.get("kind") or "",
                    "title": entry.get("title") or "",
                    "detail": entry.get("detail") or "",
                    "url": entry.get("url") or "",
                    "at": entry.get("at") or "",
                }
            )
    matched.sort(key=lambda item: item["at"], reverse=True)
    return matched[:6]


def snapshot() -> dict:
    """Return public product findings. Orders, messages, and calls stay on the signed-in account."""
    from backend.app.integrations.supabase_store import load_entries

    stored = load_entries()
    by_id = {entry["id"]: entry for entry in _entries}
    for entry in stored or []:
        current = by_id.get(entry["id"])
        if current and current.get("ballot"):
            continue
        by_id[entry["id"]] = entry
    entries = [entry for entry in by_id.values() if entry.get("kind") not in _PRIVATE_KINDS]
    entries.sort(key=lambda item: item["at"], reverse=True)
    counts = {kind: 0 for kind in _KINDS}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return {"entries": entries[:200], "counts": counts}


def _public_entries() -> list[dict]:
    """Read the public registry from Supabase, and keep any row still only in memory."""
    from backend.app.integrations.supabase_store import load_entries

    stored = load_entries()
    rows = [entry for entry in (list(_entries) if stored is None else list(stored)) if entry.get("kind") not in _PRIVATE_KINDS]
    seen = {str(entry.get("id") or "") for entry in rows}
    if stored is not None:
        for entry in _entries:
            if entry.get("kind") in _PRIVATE_KINDS:
                continue
            if str(entry.get("id") or "") not in seen:
                rows.append(entry)
    return rows


def _url_key(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    if not host:
        return ""
    return f"{host}{path}"


def _name_hit(name: str, entry: dict) -> bool:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", name.lower())
        if len(word) > 3 and word not in {"with", "from", "this", "that", "pack"}
    ]
    if len(words) < 2:
        return False
    blob = f"{entry.get('title') or ''} {entry.get('detail') or ''}".lower()
    return sum(1 for word in words[:4] if word in blob) >= 2


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
