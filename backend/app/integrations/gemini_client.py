"""Gemini client shared by semantic reasoning pipelines."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


class GeminiClient:
    """Gemini wrapper for semantic reasoning.

    Fine-print analysis and claim validation authenticate with the
    ``GEMINI_API_KEY`` environment variable. ``GEMINI_MODEL`` overrides the model.
    """

    api_key_env = "GEMINI_API_KEY"
    model_env = "GEMINI_MODEL"
    default_model = "gemini-3.8-flash"
    fallback_model = "gemini-3.5-flash-lite"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    _exhausted_until: dict[str, float] = {}

    def complete(self, prompt: str) -> str:
        """Send one prompt to Gemini and return the message text.

        The free daily allowance is counted per model. When the selected model
        is exhausted, the next request uses the lighter flash model.
        """
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        primary = os.environ.get(self.model_env) or self.default_model
        models = [primary]
        if self.fallback_model not in models:
            models.append(self.fallback_model)
        now = time.time()
        saw_quota = False
        for model in models:
            if self._exhausted_until.get(model, 0) > now:
                saw_quota = True
                continue
            try:
                return self._complete_model(model, prompt, api_key)
            except _DailyQuota:
                saw_quota = True
                continue
        if saw_quota:
            raise RuntimeError("Gemini daily quota is used")
        raise RuntimeError("Gemini request failed")

    def _complete_model(self, model: str, prompt: str, api_key: str) -> str:
        try:
            payload = _post_json(self.endpoint.format(model=model), _request_body(prompt), api_key)
        except urllib.error.HTTPError as exc:
            delay = _retry_seconds(exc)
            if exc.code in {429, 500, 503} and (delay is None or delay <= 30):
                time.sleep(1.5)
                try:
                    payload = _post_json(self.endpoint.format(model=model), _request_body(prompt), api_key)
                except urllib.error.HTTPError as retry_exc:
                    delay = _retry_seconds(retry_exc)
                    if retry_exc.code == 429 and delay and delay > 30:
                        self._exhausted_until[model] = time.time() + delay
                        raise _DailyQuota(model) from retry_exc
                    raise RuntimeError(f"Gemini request failed with status {retry_exc.code}") from retry_exc
            elif exc.code == 429 and delay and delay > 30:
                self._exhausted_until[model] = time.time() + delay
                raise _DailyQuota(model) from exc
            else:
                raise RuntimeError(f"Gemini request failed with status {exc.code}") from exc
        content = _message_text(payload)
        if not content.strip():
            raise RuntimeError("Gemini returned an empty analysis")
        return content


class _DailyQuota(Exception):
    """The selected Gemini model has used its daily allowance."""


def _request_body(prompt: str) -> bytes:
    return json.dumps(
        {
            "systemInstruction": {
                "parts": [{"text": "Return one JSON object and no other text."}]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
    ).encode()


def _post_json(url: str, body: bytes, api_key: str) -> dict:
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _retry_seconds(exc: urllib.error.HTTPError) -> float | None:
    try:
        raw = exc.read().decode("utf-8", "replace")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    for detail in error.get("details") or []:
        if not isinstance(detail, dict):
            continue
        delay = str(detail.get("retryDelay") or "")
        if not delay.endswith("s"):
            continue
        try:
            return float(delay[:-1])
        except ValueError:
            continue
    message = str(error.get("message") or "").lower()
    if "quota" in message:
        return 12 * 60 * 60
    return None


def _message_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [str(part.get("text") or "") for part in parts if not part.get("thought")]
    return "".join(texts)


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
