"""Scaffold tests for fine-print models, services, and shared clients."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.integrations.groq_client import GroqClient
from backend.app.integrations.supabase_client import SupabaseClient
from backend.app.models.fine_print import (
    FinePrintAnalysisResult,
    PolicyDocument,
    RiskCategory,
    RiskFinding,
    Severity,
)
from backend.app.services.fine_print.analysis import FinePrintAnalyzer
from backend.app.services.fine_print.extraction import FinePrintExtractor

RETRIEVED_AT = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
POLICY_URL = "https://example.com/policies/returns"


def test_fine_print_scaffolds_instantiate_without_external_calls():
    extractor = FinePrintExtractor()
    analyzer = FinePrintAnalyzer()
    groq = GroqClient()
    supabase = SupabaseClient()

    assert isinstance(extractor, FinePrintExtractor)
    assert isinstance(analyzer, FinePrintAnalyzer)
    assert groq.api_key_env == "GROQ_API_KEY"
    assert supabase.url_env == "SUPABASE_URL"
    assert supabase.key_env == "SUPABASE_KEY"


def test_valid_fine_print_analysis_result():
    document = PolicyDocument(
        url=POLICY_URL,
        extracted_text="Returns are accepted within 14 days.",
        retrieved_at=RETRIEVED_AT,
    )
    finding = RiskFinding(
        category=RiskCategory.RETURN_RESTRICTION,
        severity=Severity.HIGH,
        explanation="The return window is shorter than a typical retail policy.",
        evidence_quotation="Returns are accepted within 14 days.",
        source_url=POLICY_URL,
    )
    result = FinePrintAnalysisResult(
        document=document,
        findings=[finding],
        analyzed_at=RETRIEVED_AT,
    )

    assert result.document.extracted_text.startswith("Returns")
    assert result.findings[0].category is RiskCategory.RETURN_RESTRICTION
    assert result.findings[0].severity is Severity.HIGH
    assert result.analyzed_at == RETRIEVED_AT


def test_policy_document_requires_extracted_text():
    with pytest.raises(ValidationError):
        PolicyDocument(url=POLICY_URL, retrieved_at=RETRIEVED_AT)


def test_policy_document_rejects_empty_text_and_invalid_url():
    with pytest.raises(ValidationError):
        PolicyDocument(
            url=POLICY_URL,
            extracted_text="",
            retrieved_at=RETRIEVED_AT,
        )

    with pytest.raises(ValidationError):
        PolicyDocument(
            url="not-a-url",
            extracted_text="Returns are final.",
            retrieved_at=RETRIEVED_AT,
        )


def test_risk_finding_rejects_unknown_category_and_severity():
    with pytest.raises(ValidationError):
        RiskFinding(
            category="hidden_fee",
            severity=Severity.LOW,
            explanation="Unrecognized category.",
            evidence_quotation="A fee may apply.",
            source_url=POLICY_URL,
        )

    with pytest.raises(ValidationError):
        RiskFinding(
            category=RiskCategory.WARRANTY_EXCLUSION,
            severity="catastrophic",
            explanation="Unrecognized severity.",
            evidence_quotation="Warranty excludes wear.",
            source_url=POLICY_URL,
        )
