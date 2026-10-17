"""Independent review search for product claims."""

from datetime import datetime, timezone

from backend.app.integrations.tavily_client import TavilyClient
from backend.app.models.claim_validation import ClaimEvidence, ProductClaim


class TavilySearchService:
    """Find reviews that discuss a seller's product claim.

    The search asks Tavily for review pages about the product and the claim.
    """

    def __init__(self, search=None) -> None:
        self._search = search

    def reviews(self, claim: ProductClaim) -> list[ClaimEvidence]:
        """Return review snippets for one seller claim."""
        search = self._search or TavilyClient().search
        retrieved_at = datetime.now(timezone.utc)
        evidence: list[ClaimEvidence] = []
        for hit in search(_review_query(claim)):
            url = str(hit.get("url") or "").strip()
            quotation = str(hit.get("content") or "").strip()
            title = str(hit.get("title") or url).strip()
            if not url or not quotation or not title:
                continue
            evidence.append(
                ClaimEvidence(
                    source_url=url,
                    title=title,
                    quotation=quotation,
                    retrieved_at=retrieved_at,
                )
            )
        return evidence


def _review_query(claim: ProductClaim) -> str:
    return f'"{claim.product_name}" reviews {claim.claim_text}'
