"""Gemini client request shape and response parsing."""

import io
import json

from backend.app.integrations.gemini_client import GeminiClient


def test_complete_sends_json_to_gemini_and_returns_the_text(monkeypatch):
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["key"] = request.get_header("X-goog-api-key")
        captured["body"] = json.loads(request.data)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"thought": True, "text": "draft"},
                            {"text": '{"verdict": "supported"}'},
                        ]
                    }
                }
            ]
        }
        return Response(json.dumps(payload).encode())

    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr("backend.app.integrations.gemini_client.urllib.request.urlopen", urlopen)

    text = GeminiClient().complete("Compare this claim.")

    assert text == '{"verdict": "supported"}'
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    )
    assert captured["timeout"] == 60
    assert captured["key"] == "local-test-key"
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "Compare this claim."
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
