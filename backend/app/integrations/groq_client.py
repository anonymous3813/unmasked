"""Groq client shared by semantic reasoning pipelines."""

import json
import os
import urllib.error
import urllib.request


class GroqClient:
    """Groq wrapper for semantic reasoning.

    Fine-print analysis and claim validation authenticate with the
    ``GROQ_API_KEY`` environment variable. ``GROQ_MODEL`` overrides the model.
    """

    api_key_env = "GROQ_API_KEY"
    model_env = "GROQ_MODEL"
    default_model = "openai/gpt-oss-120b"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def complete(self, prompt: str) -> str:
        """Send one prompt to Groq and return the message text."""
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        body = json.dumps(
            {
                "model": os.environ.get(self.model_env) or self.default_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return one JSON object and no other text.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Groq request failed with status {exc.code}") from exc

        content = payload["choices"][0]["message"].get("content") or ""
        if not content.strip():
            raise RuntimeError("Groq returned an empty analysis")
        return content
