"""Scaffold tests for claim-validation models, services, and clients."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.integrations.gemini_client import GeminiClient
from backend.app.integrations.supabase_client import SupabaseClient
from backend.app.integrations.tavily_client import TavilyClient
from backend.app.models.claim_validation import (
    ClaimEvidence,
    ClaimValidationResult,
    ClaimVerdict,
    ProductClaim,
)
from backend.app.services.claim_validation.tavily_search import TavilySearchService
from backend.app.services.claim_validation.validation import ClaimValidationService

VALIDATED_AT = datetime(2026, 10, 17, 12, 30, tzinfo=timezone.utc)
CLAIM_URL = "https://example.com/products/chair"
EVIDENCE_URL = "https://example.org/reviews/chair-materials"


def test_claim_validation_scaffolds_instantiate_without_external_calls():
    search = TavilySearchService()
    validator = ClaimValidationService()
    tavily = TavilyClient()
    gemini = GeminiClient()
    supabase = SupabaseClient()

    assert isinstance(search, TavilySearchService)
    assert isinstance(validator, ClaimValidationService)
    assert isinstance(tavily, TavilyClient)
    assert tavily.api_key_env == "TAVILY_API_KEY"
    assert gemini.api_key_env == "GEMINI_API_KEY"
    assert supabase.url_env == "SUPABASE_URL"
    assert supabase.key_env == "SUPABASE_KEY"


def test_valid_claim_validation_result():
    claim = ProductClaim(
        claim_text="The cushion is made from recycled ocean plastic.",
        product_name="Example Chair",
        source_url=CLAIM_URL,
    )
    evidence = ClaimEvidence(
        source_url=EVIDENCE_URL,
        title="Independent materials review",
        quotation="The cushion uses virgin polyester, not ocean plastic.",
        retrieved_at=VALIDATED_AT,
    )
    result = ClaimValidationResult(
        claim=claim,
        verdict=ClaimVerdict.CONTRADICTED,
        explanation="The independent review names a different cushion material.",
        evidence=[evidence],
        validated_at=VALIDATED_AT,
    )

    assert result.claim.product_name == "Example Chair"
    assert result.verdict is ClaimVerdict.CONTRADICTED
    assert result.evidence[0].title == "Independent materials review"
    assert result.validated_at == VALIDATED_AT


def test_product_claim_requires_claim_text_and_product_name():
    with pytest.raises(ValidationError):
        ProductClaim(product_name="Example Chair", source_url=CLAIM_URL)

    with pytest.raises(ValidationError):
        ProductClaim(
            claim_text="Made from recycled ocean plastic.",
            source_url=CLAIM_URL,
        )


def test_claim_models_reject_blank_text_and_invalid_verdict():
    with pytest.raises(ValidationError):
        ProductClaim(
            claim_text="",
            product_name="Example Chair",
            source_url=CLAIM_URL,
        )

    claim = ProductClaim(
        claim_text="The cushion is waterproof.",
        product_name="Example Chair",
        source_url=CLAIM_URL,
    )
    with pytest.raises(ValidationError):
        ClaimValidationResult(
            claim=claim,
            verdict="unverified",
            explanation="No matching verdict.",
            evidence=[],
            validated_at=VALIDATED_AT,
        )


def test_claim_evidence_rejects_invalid_source_url():
    with pytest.raises(ValidationError):
        ClaimEvidence(
            source_url="not-a-url",
            title="Lab report",
            quotation="No waterproof rating was found.",
            retrieved_at=VALIDATED_AT,
        )
