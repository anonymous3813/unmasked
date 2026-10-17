"""Groq client shared by semantic reasoning pipelines."""


class GroqClient:
    """Minimal Groq wrapper for later semantic reasoning.

    Both fine-print analysis and claim validation will authenticate with
    the ``GROQ_API_KEY`` environment variable. This scaffold does not read
    secrets and does not send API requests.
    """

    api_key_env = "GROQ_API_KEY"
