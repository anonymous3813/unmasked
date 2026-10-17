"""Credibility and relevance checks for product-claim evidence."""


class ClaimValidationService:
    """Judge whether independent evidence supports or contradicts a claim.

    Future implementations will use Groq to evaluate credibility and
    relevance, then persist findings and citations through Supabase.
    This scaffold performs no validation and makes no external requests.
    """
