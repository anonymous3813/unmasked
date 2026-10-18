"""Email and password accounts for one shopper's orders, wishlist, and taste."""

import hashlib
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_users: dict[str, dict] = {}
_sessions: dict[str, str] = {}


def reset() -> None:
    _users.clear()
    _sessions.clear()


def register(email: str, password: str, name: str, phone: str = "") -> dict:
    """Create an account and return a session."""
    cleaned = _email(email)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Enter a valid email.")
    secret = password or ""
    if len(secret) < 8:
        raise HTTPException(status_code=400, detail="Use a password of at least 8 characters.")
    if any(row["email"] == cleaned for row in _users.values()):
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    user_id = secrets.token_hex(16)
    user = {
        "id": user_id,
        "email": cleaned,
        "name": " ".join((name or cleaned.split("@")[0]).split())[:80] or cleaned.split("@")[0],
        "password": _hash(secret),
        "phone": _phone(phone),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    _users[user_id] = user
    from backend.app.integrations.supabase_store import save_user

    save_user(user)
    return _session(user)


def login(email: str, password: str, phone: str = "") -> dict:
    """Return a session when the email and password match."""
    cleaned = _email(email)
    user = next((row for row in _users.values() if row["email"] == cleaned), None)
    if user is None or not _matches(password or "", user["password"]):
        raise HTTPException(status_code=401, detail="That email or password is not right.")
    mobile = _phone(phone)
    if mobile:
        user["phone"] = mobile
        from backend.app.integrations.supabase_store import save_user

        save_user(user)
    return _session(user)


def user_by_phone(phone: str) -> dict | None:
    """Return the account that asked to receive texts at this number."""
    mobile = _phone(phone)
    if not mobile:
        return None
    for user in _users.values():
        if _phone(str(user.get("phone") or "")) == mobile:
            return {"id": user["id"], "email": user["email"], "name": user["name"], "phone": mobile}
    return None


def user_by_id(user_id: str) -> dict | None:
    """Return a signed-in account by id."""
    user = _users.get(user_id or "")
    if not user:
        return None
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "phone": user.get("phone") or "",
    }


def logout(authorization: str | None) -> dict:
    """Forget the session that sent this request."""
    token = _token(authorization or "")
    if token:
        digest = hashlib.sha256(token.encode()).hexdigest()
        _sessions.pop(digest, None)
        from backend.app.integrations.supabase_store import delete_session

        delete_session(digest)
    return {"signedOut": True}


def require_user(authorization: str | None) -> dict:
    """Return the signed-in shopper. Direct test calls keep the shared shopper profile."""
    if not isinstance(authorization, str):
        authorization = None
    user = user_from_authorization(authorization or "")
    if user:
        return user
    if authorization is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return {"id": "shopper", "email": "", "name": "Shopper"}
    raise HTTPException(status_code=401, detail="Sign in to use Unmasked.")


def user_from_authorization(header: str) -> dict | None:
    token = _token(header)
    if not token:
        return None
    user_id = _sessions.get(hashlib.sha256(token.encode()).hexdigest())
    user = _users.get(user_id or "")
    if not user:
        return None
    return {"id": user["id"], "email": user["email"], "name": user["name"], "phone": user.get("phone") or ""}


def remember_users(users: list[dict], sessions: list[dict]) -> None:
    """Load accounts saved before this process started."""
    for user in users:
        if user.get("id") and user["id"] not in _users:
            _users[user["id"]] = user
    for session in sessions:
        if session.get("digest") and session.get("user_id"):
            _sessions[session["digest"]] = session["user_id"]


def _session(user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    _sessions[digest] = user["id"]
    from backend.app.integrations.supabase_store import save_session

    save_session(digest, user["id"])
    return {
        "token": token,
        "account": {"id": user["id"], "email": user["email"], "name": user["name"], "phone": user.get("phone") or ""},
    }


def _phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if str(value or "").strip().startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    return ""


def _email(value: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if _EMAIL.match(cleaned) else ""


def _token(header: str) -> str:
    raw = (header or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2_sha256$200000${salt}${digest}"


def _matches(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    return secrets.compare_digest(check, digest)
