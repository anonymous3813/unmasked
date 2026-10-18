"""Pydantic models for product claim validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ClaimVerdict(str, Enum):
    """How independent evidence relates to a product claim."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class ComparisonAspect(str, Enum):
    """Shopper concerns used when recommending another product."""

    ENVIRONMENTAL = "environmental"
    COST_VALUE = "cost_value"
    DURABILITY = "durability"


class ProductClaim(BaseModel):
    """A claim the seller makes about a product."""

    claim_text: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    source_url: HttpUrl
    category: str | None = None


class ClaimEvidence(BaseModel):
    """An independent citation relevant to a product claim."""

    source_url: HttpUrl
    title: str = Field(min_length=1)
    quotation: str = Field(min_length=1)
    retrieved_at: datetime


class ClaimValidationResult(BaseModel):
    """The outcome of checking one product claim against independent evidence."""

    claim: ProductClaim
    verdict: ClaimVerdict
    explanation: str = Field(min_length=1)
    evidence: list[ClaimEvidence]
    validated_at: datetime


class ProductRecommendation(BaseModel):
    """Another product a review supports on one shopper concern."""

    product_name: str = Field(min_length=1)
    aspect: ComparisonAspect
    reason: str = Field(min_length=1)
    source_url: HttpUrl
    evidence_quotation: str = Field(min_length=1)


class ClaimAnalysis(BaseModel):
    """Claim verdicts plus other products the reviews support."""

    product_name: str = Field(min_length=1)
    validations: list[ClaimValidationResult]
    recommendations: list[ProductRecommendation]
    analyzed_at: datetime
