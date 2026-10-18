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
    DAMAGE_POLICY = "damage_policy"
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


class PriceWithTax(BaseModel):
    """A listed price and the tax-inclusive amount when the page does not show it."""

    listed_price: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    tax_included: bool
    price_with_tax: str | None = None
    tax_rate: str | None = None
    explanation: str = Field(min_length=1)
    evidence_quotation: str = Field(min_length=1)
    source_url: HttpUrl


class FinePrintAnalysisResult(BaseModel):
    """Concerns and price details that are not already visible on the product page."""

    document: PolicyDocument
    findings: list[RiskFinding]
    analyzed_at: datetime
    price: PriceWithTax | None = None


class FinePrintExtraction(BaseModel):
    """Product details and the policy documents found from one page."""

    source_url: HttpUrl
    page_text: str = Field(min_length=1)
    documents: list[PolicyDocument]
    retrieved_at: datetime


class NotificationKind(str, Enum):
    """What a shopper notification is about."""

    CONCERN = "concern"
    PRICE = "price"
    PRODUCT_INFO = "product_info"


class ProductNotification(BaseModel):
    """One piece of product information to show the shopper."""

    kind: NotificationKind
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_url: HttpUrl
    created_at: datetime
    severity: Severity | None = None
