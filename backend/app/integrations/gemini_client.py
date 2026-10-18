"""Gemini client shared by semantic reasoning pipelines."""

import json
import os
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
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def complete(self, prompt: str) -> str:
        """Send one prompt to Gemini and return the message text."""
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        model = os.environ.get(self.model_env) or self.default_model
        body = json.dumps(
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
        request = urllib.request.Request(
            self.endpoint.format(model=model),
            data=body,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Gemini request failed with status {exc.code}") from exc

        content = _message_text(payload)
        if not content.strip():
            raise RuntimeError("Gemini returned an empty analysis")
        return content


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
