"""Tavily client for independent product-claim research."""


class TavilyClient:
    """Minimal Tavily wrapper for later evidence search.

    Claim validation will authenticate with the ``TAVILY_API_KEY``
    environment variable. This scaffold does not read secrets and does
    not send search requests.
    """

    api_key_env = "TAVILY_API_KEY"
