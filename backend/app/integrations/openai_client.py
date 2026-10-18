"""OpenAI client for the shopper's agent."""

import json
import os
import urllib.error
import urllib.request

from backend.app.integrations.gemini_client import _load_local_env


def _product_payload(raw: str) -> dict:
    start = (raw or "").find("{")
    end = (raw or "").rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "name": str(payload.get("name") or "").strip()[:120],
        "brand": str(payload.get("brand") or "").strip()[:80],
        "kind": str(payload.get("kind") or "").strip()[:60],
        "query": str(payload.get("query") or "").strip()[:120],
    }


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
        content = self._chat(
            api_key,
            model,
            [
                {"role": "system", "content": "Return one JSON object and no other text."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=900,
            json_object=True,
        )
        if not content.strip():
            raise RuntimeError("OpenAI returned an empty analysis")
        return content

    def _chat(
        self,
        api_key: str,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int,
        json_object: bool,
    ) -> str:
        bodies = [
            {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
                "reasoning_effort": "minimal",
            },
            {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
            },
        ]
        if json_object:
            for body in bodies:
                body["response_format"] = {"type": "json_object"}
        last_error = "OpenAI request failed"
        for body in bodies:
            request = urllib.request.Request(
                self.endpoint,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                last_error = f"OpenAI request failed with status {exc.code}"
                continue
            choices = payload.get("choices") or []
            if not choices:
                last_error = "OpenAI returned an empty analysis"
                continue
            content = str((choices[0].get("message") or {}).get("content") or "")
            if content.strip():
                return content
            last_error = "OpenAI returned an empty analysis"
        raise RuntimeError(last_error)

    def read_image(self, data: bytes, mime: str) -> str:
        """Read product lines from a bill photo."""
        import base64

        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get(self.model_env) or self.default_model
        encoded = base64.b64encode(data).decode("ascii")
        return self._chat(
            api_key,
            model,
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Read this bill image. Put each purchased product on its own line, "
                                "then its item price with the currency symbol printed on the bill (£, $, or €). "
                                "Keep the product name. "
                                "Write returned at the end of a line only when that bill marks the product returned or refunded. "
                                "Leave out shipping, delivery, tax, VAT, promotions, discounts, and totals. "
                                "No other text."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
            max_tokens=700,
            json_object=False,
        )

    def identify_product(self, data: bytes, mime: str = "image/jpeg") -> dict:
        """Name a retail product in a shopper photo for store search."""
        import base64

        from backend.app.services.shop.photo import prepare_image

        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get(self.model_env) or self.default_model
        data, media = prepare_image(data, mime)
        if not data:
            return {}
        if len(data) > 4_500_000:
            data = data[:4_500_000]
        encoded = base64.b64encode(data).decode("ascii")
        media = media if str(media or "").startswith("image/") else "image/jpeg"
        prompt = (
            "This is a shopper photo. Identify the retail product for shopping search. "
            "Do not identify people, faces, or private documents. "
            "If it is not a clear product, leave query empty. "
            'Return JSON: {"name":"product name","brand":"brand or empty","kind":"short kind",'
            '"query":"3-8 word store search query"}'
        )
        messages = [
            {"role": "system", "content": "Return one JSON object and no other text."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{media};base64,{encoded}"}},
                ],
            },
        ]
        raw = ""
        try:
            raw = self._chat(api_key, model, messages, max_tokens=400, json_object=True)
        except RuntimeError:
            try:
                raw = self._chat(api_key, model, messages, max_tokens=400, json_object=False)
            except RuntimeError:
                raw = ""
        parsed = _product_payload(raw)
        if parsed.get("query") or parsed.get("name"):
            return parsed
        # Gemini often accepts the same JPEG when OpenAI vision is picky.
        try:
            from backend.app.integrations.gemini_client import identify_product_image

            return identify_product_image(data, media)
        except Exception:
            return parsed
