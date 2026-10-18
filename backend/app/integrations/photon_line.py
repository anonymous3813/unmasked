"""The Spectrum iMessage number for this project.

Photon 2.0 uses a bearer key and a project id that starts with pho_prj_.
These credentials are a Spectrum project id and project secret, so the line
is read from the Stable Spectrum API.
"""

import base64
import json
import os
import urllib.error
import urllib.request
import uuid

from backend.app.integrations.gemini_client import _load_local_env

_cached: dict | None = None


def send_intro(text: str) -> dict:
    """Text the shopper the first summary. Photon 2.0 sends it when the agent already has a space."""
    _load_local_env()
    message = " ".join(str(text or "").split())
    if not message:
        message = "Your Online Assistant checked a product. The page had no policy updates."
    api_key = os.environ.get("PHOTON_API_KEY", "")
    project_id = os.environ.get("PHOTON_PROJECT_ID") or ""
    sender_id = os.environ.get("PHOTON_AGENT_USER_ID", "")
    space_id = os.environ.get("PHOTON_SPACE_ID", "")
    if not api_key.startswith("pho_") or not sender_id.startswith("pho_usr_") or not space_id.startswith("pho_spc_"):
        return {
            "sent": False,
            "reason": (
                "Photon 2.0 did not send this text. It needs an API key starting with pho_, "
                "a pho_prj_ project, a pho_usr_ agent, and a pho_spc_ space. "
                "The Spectrum project id cannot send it, and the shopper has to text the shared line once before a reply can arrive."
            ),
        }
    if not project_id.startswith("pho_prj_"):
        return {
            "sent": False,
            "reason": "Set PHOTON_PROJECT_ID to the Photon 2.0 project id that starts with pho_prj_.",
        }
    status, _payload, detail = _bearer(
        "POST",
        f"/v1/projects/{project_id}/messages",
        api_key,
        {
            "senderId": sender_id,
            "spaceId": space_id,
            "content": {"type": "text", "format": "plain", "text": message[:1000]},
        },
    )
    if status == 200:
        return {"sent": True}
    return {"sent": False, "reason": detail or "Photon did not accept the text."}


def _bearer(method: str, path: str, api_key: str, body: dict) -> tuple[int, dict, str]:
    request = urllib.request.Request(
        "https://api.photon.codes" + path,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "UnmaskedShop/1.0",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}, _error_detail(exc.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}, ""
    return 200, payload if isinstance(payload, dict) else {}, ""


def agent_line() -> dict:
    """Return the project's iMessage number, creating one dedicated line if the project has none."""
    global _cached
    if _cached is not None:
        return _cached
    loaded = _load_line()
    if loaded["status"] != "unavailable":
        _cached = loaded
    return loaded


def _load_line() -> dict:
    _load_local_env()
    project_id = os.environ.get("PHOTON_PROJECT_ID") or os.environ.get("PHOTON_PROJECT_I")
    secret = os.environ.get("PHOTON_PROJECT_SECRET")
    if not project_id or not secret:
        return {"phone": "", "status": "missing_credentials"}
    status, data, detail = _request("GET", f"/projects/{project_id}/lines/", project_id, secret)
    if status in {401, 403}:
        return {"phone": "", "status": "rejected", "detail": detail}
    if status != 200:
        return {"phone": "", "status": "unavailable", "detail": detail}
    for line in data.get("lines") or []:
        phone = str(line.get("phoneNumber") or "")
        if phone:
            return {"phone": phone, "status": "ready"}
    user_status, users, user_detail = _request("GET", f"/projects/{project_id}/users/", project_id, secret)
    if user_status == 200:
        for user in users.get("users") or []:
            phone = str(user.get("assignedPhoneNumber") or "")
            if phone:
                return {"phone": phone, "status": "ready"}
    sender = os.environ.get("PHOTON_SENDER") or os.environ.get("PHOTON_TEST_SENDER")
    if sender:
        created, payload, detail = _request(
            "POST",
            f"/projects/{project_id}/users/",
            project_id,
            secret,
            {"type": "shared", "phoneNumber": sender, "firstName": "Shopper"},
        )
        phone = str(payload.get("assignedPhoneNumber") or "")
        if phone:
            return {"phone": phone, "status": "ready"}
        return {"phone": "", "status": "no_line", "detail": detail}
    return {"phone": "", "status": "needs_sender", "detail": user_detail or detail}


def _request(
    method: str,
    path: str,
    project_id: str,
    secret: str,
    body: dict | None = None,
) -> tuple[int, dict, str]:
    token = base64.b64encode(f"{project_id}:{secret}".encode()).decode()
    request = urllib.request.Request(
        "https://spectrum.photon.codes" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "UnmaskedShop/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}, _error_detail(exc.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}, ""
    data = payload.get("data")
    return 200, data if isinstance(data, dict) else {}, ""


def _error_detail(raw: bytes) -> str:
    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return ""
    detail = body.get("detail") or body.get("title") or body.get("message") or ""
    if not isinstance(detail, str):
        return ""
    return detail[:180]
