"""Pydantic models for fine-print risk analysis."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class RiskCategory(str, Enum):
    """Consumer-risk categories a policy passage can indicate."""

    RETURN_RESTRICTION = "return_restriction"
    RESTOCKING_FEE = "restocking_fee"
    CANCELLATION_TRAP = "cancellation_trap"
    WARRANTY_EXCLUSION = "warranty_exclusion"
    OTHER = "other"


class Severity(str, Enum):
    """How serious a fine-print finding is for the shopper."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyDocument(BaseModel):
    """A policy page and the text extracted from it."""

    url: HttpUrl
    extracted_text: str = Field(min_length=1)
    retrieved_at: datetime


class RiskFinding(BaseModel):
    """One evidence-backed consumer risk found in a policy document."""

    category: RiskCategory
    severity: Severity
    explanation: str = Field(min_length=1)
    evidence_quotation: str = Field(min_length=1)
    source_url: HttpUrl


class FinePrintAnalysisResult(BaseModel):
    """The outcome of analyzing one policy document."""

    document: PolicyDocument
    findings: list[RiskFinding]
    analyzed_at: datetime
