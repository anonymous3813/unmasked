"""Gemini client request shape and response parsing."""

import io
import json
import urllib.error

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


def test_daily_quota_uses_the_lighter_model(monkeypatch):
    GeminiClient._exhausted_until.clear()
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("models/gemini-3.8-flash:generateContent"):
            body = json.dumps(
                {"error": {"message": "Quota exceeded", "details": [{"retryDelay": "70000s"}]}}
            ).encode()
            raise urllib.error.HTTPError(request.full_url, 429, "quota", hdrs=None, fp=io.BytesIO(body))
        payload = {"candidates": [{"content": {"parts": [{"text": '{"answer": "ok"}'}]}}]}
        return Response(json.dumps(payload).encode())

    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr("backend.app.integrations.gemini_client.urllib.request.urlopen", urlopen)

    text = GeminiClient().complete("What is the return policy?")

    assert text == '{"answer": "ok"}'
    assert calls[0].endswith("models/gemini-3.8-flash:generateContent")
    assert calls[1].endswith("models/gemini-3.5-flash-lite:generateContent")
