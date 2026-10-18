"""Two rounds of agent votes before a line enters the registry."""

import re

_AGENTS = (
    ("Ada", "page reader"),
    ("Basil", "duplicate clerk"),
    ("Cora", "detail reader"),
    ("Dex", "link checker"),
    ("Esther", "record keeper"),
    ("Fern", "time clerk"),
    ("Gale", "scope clerk"),
)


def deliberate(entry: dict, previous: dict | None = None) -> dict:
    """Let the other agents vote, hear each other, and vote once more."""
    first = [_first(name, role, entry, previous) for name, role in _AGENTS]
    second = [_second(vote, first) for vote in first]
    yes = sum(1 for vote in second if vote["vote"] == "yes")
    quorum = _quorum()
    admitted = _commits(second)
    decision = (
        "The table admitted this entry."
        if admitted
        else "The table kept this entry out."
    )
    return {
        "entryId": entry.get("id") or "",
        "rounds": [{"name": "First vote", "agents": first}, {"name": "Second vote", "agents": second}],
        "admitted": admitted,
        "quorum": quorum,
        "yes": yes,
        "decision": decision,
    }


def _first(name: str, role: str, entry: dict, previous: dict | None) -> dict:
    title = str(entry.get("title") or "").strip()
    detail = str(entry.get("detail") or "").strip()
    url = str(entry.get("url") or "").strip()
    kind = str(entry.get("kind") or "").strip()
    host = _host(url)
    if name == "Ada":
        ok = len(title) >= 3
        reason = f"The line names {title}." if ok else "The line does not name what was added."
    elif name == "Basil":
        same = previous is not None and previous.get("title") == title and previous.get("detail") == detail and previous.get("url") == url
        ok = not same
        reason = "This repeats the line already on the table." if same else "This is not a copy of the last line."
    elif name == "Cora":
        ok = len(detail) >= 12 and not detail.lower().startswith("no policy notes")
        reason = f"The note says: {detail}" if ok else "The note is too thin to stand on its own."
    elif name == "Dex":
        ok = not url or url.startswith("https://") or url.startswith("http://")
        reason = f"The address is {host}." if ok and host else "There is no page address on this line." if ok else "The address is not a page link."
    elif name == "Fern":
        ok = bool(str(entry.get("at") or "").strip())
        reason = "The line carries a time." if ok else "The line has no time, so it cannot be ordered."
    elif name == "Gale":
        ok = len(title) >= 3 and len(detail) >= 8
        reason = "The title and the note are both there." if ok else "The title and the note do not both earn a place."
    else:
        ok = kind in {"page", "ask", "message", "call", "order", "intro"}
        article = "an" if kind[:1].lower() in "aeiou" else "a"
        reason = f"This is {article} {kind} record." if ok else "This is not a kind of record the registry keeps."
    story = _story(name, reason, "yes" if ok else "no", heard=False, first=name == "Ada")
    return {"name": name, "role": role, "vote": "yes" if ok else "no", "reason": reason, "story": story, "hard": name in {"Ada", "Basil", "Dex", "Esther", "Fern"} and not ok}


def _second(vote: dict, first: list[dict]) -> dict:
    yes = sum(1 for item in first if item["vote"] == "yes")
    heard = next(item["reason"] for item in first if item["name"] != vote["name"])
    if vote["vote"] == "no" and not vote["hard"] and yes >= _quorum():
        reason = f"After hearing the others, {vote['name']} let the thin note stand."
        return {**vote, "vote": "yes", "reason": reason, "story": _story(vote["name"], reason, "yes", heard=True), "hard": False}
    if vote["vote"] == "no" and vote["hard"]:
        reason = vote["reason"]
        story = f"After the others had spoken, {vote['name']} still would not sign. {reason}"
        return {**vote, "story": story}
    reason = f"{vote['name']} heard that {heard[0].lower()}{heard[1:]} and stayed with the same vote."
    return {**vote, "reason": reason, "story": _story(vote["name"], vote["reason"], vote["vote"], heard=True)}


def _quorum() -> int:
    """A line is added only when a majority of the agents vote yes."""
    return len(_AGENTS) // 2 + 1


def _commits(votes: list[dict]) -> bool:
    yes = sum(1 for vote in votes if vote.get("vote") == "yes")
    blocked = any(vote.get("vote") == "no" and vote.get("hard") for vote in votes)
    return yes >= _quorum() and not blocked


def _story(name: str, reason: str, vote: str, heard: bool, first: bool = False) -> str:
    side = "to let it in" if vote == "yes" else "to keep it out"
    if heard:
        return f"{name} looked around the table. {reason} The second vote was {side}."
    opener = f"{name} spoke first." if first else f"{name} spoke next."
    return f"{opener} {reason} The vote was {side}."


def _host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url)
    return match.group(1) if match else ""
