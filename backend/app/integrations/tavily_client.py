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

    def search(
        self,
        query: str,
        *,
        include_raw_content: bool = False,
        include_images: bool = False,
        max_results: int = 5,
        search_depth: str = "basic",
    ) -> list[dict]:
        """Return Tavily result objects for one search query."""
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")

        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": search_depth,
            "topic": "general",
            "max_results": max_results,
            "include_answer": False,
        }
        if include_raw_content:
            payload["include_raw_content"] = True
        if include_images:
            payload["include_images"] = True
        wants_images = include_images
        body = json.dumps(payload).encode()
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
        results = [result for result in (payload.get("results") or []) if isinstance(result, dict)]
        images = payload.get("images") or []
        if wants_images and images:
            for result, image in zip(results, images):
                url = image if isinstance(image, str) else (image or {}).get("url")
                if url and not result.get("image"):
                    result["image"] = url
        return results

    def extract(self, urls: list[str]) -> list[dict]:
        """Return page text for product URLs that the search snippet did not price."""
        _load_local_env()
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")
        body = json.dumps({"api_key": api_key, "urls": urls[:5]}).encode()
        request = urllib.request.Request(
            "https://api.tavily.com/extract",
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
