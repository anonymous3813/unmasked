"""OpenAI client request shape and response parsing."""

import io
import json

from backend.app.integrations.openai_client import OpenAIClient


def test_complete_sends_json_to_openai_and_returns_the_text(monkeypatch):
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data)
        payload = {"choices": [{"message": {"content": '{"answer": "The page lists recycled wool."}'}}]}
        return Response(json.dumps(payload).encode())

    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    monkeypatch.setattr("backend.app.integrations.openai_client.urllib.request.urlopen", urlopen)

    text = OpenAIClient().complete("What is on this page?")

    assert text == '{"answer": "The page lists recycled wool."}'
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["timeout"] == 45
    assert captured["auth"] == "Bearer local-test-key"
    assert captured["body"]["model"] == "gpt-5-mini"
    assert captured["body"]["messages"][1]["content"] == "What is on this page?"
    assert captured["body"]["response_format"] == {"type": "json_object"}
