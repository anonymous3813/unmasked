"""The Spectrum iMessage number for this project.

Photon 2.0 uses a bearer key and a project id that starts with pho_prj_.
These credentials are a Spectrum project id and project secret, so the line
is read from the Stable Spectrum API.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
import uuid

from backend.app.integrations.gemini_client import _load_local_env

_cached: dict | None = None


def send_intro(text: str, to_number: str = "") -> dict:
    """Text the shopper a welcome over SMS, or point them to the iMessage line."""
    _load_local_env()
    message = " ".join(str(text or "").split())
    if not message:
        message = "Welcome to Unmasked. Text this number with a question, a photo, or an order."
    destination = _e164(to_number)
    agent_sms = _e164(os.environ.get("PHOTON_AGENT_SMS_NUMBER", ""))
    agent_imessage = _e164(os.environ.get("PHOTON_AGENT_IMESSAGE_NUMBER", ""))
    if destination and agent_sms and destination == agent_sms:
        return {
            "sent": False,
            "reason": "That number is the agent's line. Enter the mobile phone that should receive the text.",
        }
    if destination and agent_imessage and destination == agent_imessage:
        return {
            "sent": False,
            "reason": "That number is the agent's iMessage line. Enter your own mobile number.",
        }
    ready = _sms_ready()
    if ready is None:
        project_id, api_key, sender_id = _sms_identity()
        space_id = os.environ.get("PHOTON_SPACE_ID", "")
        if space_id.startswith("pho_spc_"):
            return _send_message(project_id, api_key, sender_id, space_id, message)
        if destination:
            status, user, detail = _bearer(
                "POST",
                f"/v1/projects/{project_id}/users",
                api_key,
                {"platform": "sms", "handle": destination},
            )
            shopper_id = _prefixed(user, "pho_usr_")
            if shopper_id:
                status, space, detail = _bearer(
                    "POST",
                    f"/v1/projects/{project_id}/spaces",
                    api_key,
                    {"platform": "sms", "participantIds": [sender_id, shopper_id]},
                )
                opened = _prefixed(space, "pho_spc_")
                if opened:
                    sent = _send_message(project_id, api_key, sender_id, opened, message)
                    if sent.get("sent"):
                        return sent
                    detail = sent.get("reason") or detail
            if agent_imessage:
                return {
                    "sent": False,
                    "reason": (
                        f"SMS is waiting on the carrier. From your iPhone, open Messages and text {agent_imessage} first. "
                        "Unmasked will reply on that thread."
                    ),
                }
            return {"sent": False, "reason": detail or "Photon did not open an SMS conversation."}
    if agent_imessage:
        return {
            "sent": False,
            "reason": (
                f"From your iPhone, open Messages and text {agent_imessage} first. "
                "A shared iMessage line replies after you write. Unmasked answers that thread."
            ),
        }
    if ready is not None:
        return ready
    if not destination:
        return {
            "sent": False,
            "reason": "Sign in with the mobile number that should receive the Unmasked welcome text.",
        }
    return {"sent": False, "reason": "Photon did not send the welcome text."}


def send_to_space(space_id: str, text: str, sender_id: str = "") -> dict:
    """Reply in a Photon conversation that already has a message from the shopper."""
    _load_local_env()
    project_id = os.environ.get("PHOTON_PROJECT_ID") or ""
    api_key = os.environ.get("PHOTON_API_KEY", "")
    agent = (
        sender_id
        if str(sender_id).startswith("pho_usr_")
        else (
            os.environ.get("PHOTON_IMESSAGE_USER_ID")
            or os.environ.get("PHOTON_AGENT_USER_ID")
            or os.environ.get("PHOTON_USER_ID")
            or ""
        )
    )
    if not api_key.startswith("pho_") or not project_id.startswith("pho_prj_") or not str(agent).startswith("pho_usr_"):
        return {
            "sent": False,
            "reason": "Photon needs PHOTON_API_KEY, PHOTON_PROJECT_ID, and an agent user id to reply.",
        }
    if not str(space_id).startswith("pho_spc_"):
        return {"sent": False, "reason": "The incoming text did not include a conversation id."}
    return _send_message(project_id, api_key, agent, space_id, text)


def _sms_identity() -> tuple[str, str, str]:
    return (
        os.environ.get("PHOTON_PROJECT_ID") or "",
        os.environ.get("PHOTON_API_KEY", ""),
        os.environ.get("PHOTON_AGENT_USER_ID") or os.environ.get("PHOTON_USER_ID") or "",
    )


def _sms_ready() -> dict | None:
    project_id, api_key, sender_id = _sms_identity()
    if sender_id == "pho_usr_00000000000000000000000001":
        return {
            "sent": False,
            "reason": (
                "PHOTON_USER_ID is the sample id from the Photon docs. "
                "Replace it with the pho_usr_ id returned for your SMS number."
            ),
        }
    if not api_key.startswith("pho_") or not sender_id.startswith("pho_usr_") or not project_id.startswith("pho_prj_"):
        return {
            "sent": False,
            "reason": (
                "Photon SMS needs PHOTON_API_KEY, PHOTON_PROJECT_ID starting with pho_prj_, "
                "and PHOTON_USER_ID starting with pho_usr_."
            ),
        }
    return None


def _send_message(project_id: str, api_key: str, sender_id: str, space_id: str, message: str) -> dict:
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
    if status in {200, 202}:
        return {"sent": True, "spaceId": space_id}
    return {"sent": False, "reason": detail or "Photon did not accept the text."}


def _prefixed(payload: dict, prefix: str) -> str:
    found = re.findall(prefix + r"[0-9a-z]+", json.dumps(payload or {}))
    return found[0] if found else ""


def _e164(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if raw.startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    return ""


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
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        return exc.code, {}, _error_detail(exc.read())
    except (urllib.error.URLError, TimeoutError):
        return 0, {}, ""
    if not raw:
        return status, {}, ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return status, {}, ""
    return status, payload if isinstance(payload, dict) else {}, ""


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
