"""Tavily client for independent product-claim research."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


class TavilyClient:
    """Search Tavily for independent pages about a product claim.

    Claim validation authenticates with ``TAVILY_API_KEY`` from the
    environment or ``backend/.env``.
    """

    api_key_env = "TAVILY_API_KEY"
    endpoint = "https://api.tavily.com/search"

    def search(self, query: str) -> list[dict]:
        """Return Tavily result objects for one search query."""
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")

        body = json.dumps(
            {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "topic": "general",
                "max_results": 5,
                "include_answer": False,
            }
        ).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Tavily request failed with status {exc.code}") from exc
        results = payload.get("results") or []
        return [result for result in results if isinstance(result, dict)]


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
