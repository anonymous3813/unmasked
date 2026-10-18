"""OpenAI client for the shopper's agent."""

import json
import os
import urllib.error
import urllib.request

from backend.app.integrations.gemini_client import _load_local_env


class OpenAIClient:
    """Chat completion client. ``OPENAI_API_KEY`` authenticates. ``OPENAI_MODEL`` overrides the model."""

    api_key_env = "OPENAI_API_KEY"
    model_env = "OPENAI_MODEL"
    default_model = "gpt-5-mini"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def complete(self, prompt: str) -> str:
        """Send one prompt and return the JSON message text."""
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get(self.model_env) or self.default_model
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Return one JSON object and no other text."},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_completion_tokens": 900,
                "reasoning_effort": "minimal",
            }
        ).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI request failed with status {exc.code}") from exc
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI returned an empty analysis")
        content = str((choices[0].get("message") or {}).get("content") or "")
        if not content.strip():
            raise RuntimeError("OpenAI returned an empty analysis")
        return content
