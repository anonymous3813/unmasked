"""Typed blocks for a shopping report. The model never supplies HTML."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _BlockModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


EvidenceStatus = Literal[
    "verified",
    "manufacturer_claim",
    "insufficient_evidence",
    "contradicted",
    "unavailable",
]

SourceClass = Literal[
    "independent_product",
    "manufacturer",
    "customer_review",
    "certification",
    "background",
]


class Source(_BlockModel):
    id: str
    title: str
    url: str
    domain: str
    retrieved_at: str | None = Field(default=None, alias="retrievedAt")
    excerpt: str
    source_class: SourceClass = Field(alias="sourceClass")
    product_specific: bool = Field(alias="productSpecific")


class Finding(_BlockModel):
    label: str
    value: str
    status: EvidenceStatus
    source_ids: list[str] = Field(default_factory=list, alias="sourceIds")


class SummaryCard(_BlockModel):
    type: Literal["summary_card"] = "summary_card"
    verdict: str
    why: str


class SustainabilityReport(_BlockModel):
    type: Literal["sustainability_report"] = "sustainability_report"
    title: str
    status: EvidenceStatus
    findings: list[Finding] = Field(default_factory=list)


class MissingEvidence(_BlockModel):
    type: Literal["missing_evidence"] = "missing_evidence"
    metric: str
    reason: str


class SourceList(_BlockModel):
    type: Literal["source_list"] = "source_list"
    source_ids: list[str] = Field(default_factory=list, alias="sourceIds")


class FollowUpBlock(_BlockModel):
    type: Literal["follow_up"] = "follow_up"
    question: str


class CompareAction(_BlockModel):
    type: Literal["compare_alternatives"]
    label: str


class SaveAction(_BlockModel):
    type: Literal["save_product"]
    label: str
    url: str


class OpenSourceAction(_BlockModel):
    type: Literal["open_source"]
    label: str
    url: str


class OpenProductAction(_BlockModel):
    type: Literal["open_product"]
    label: str
    url: str


class AskAction(_BlockModel):
    type: Literal["ask_follow_up"]
    label: str
    question: str


Action = Annotated[
    CompareAction | SaveAction | OpenSourceAction | OpenProductAction | AskAction,
    Field(discriminator="type"),
]


class SuggestedActionBlock(_BlockModel):
    type: Literal["suggested_action"] = "suggested_action"
    action: Action


Block = Annotated[
    SummaryCard | SustainabilityReport | MissingEvidence | SourceList | SuggestedActionBlock | FollowUpBlock,
    Field(discriminator="type"),
]


class ShoppingReport(_BlockModel):
    response_id: str = Field(alias="responseId")
    summary: str
    demo: Literal[False] = False
    blocks: list[Block] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    suggested_actions: list[Action] = Field(default_factory=list, alias="suggestedActions")
    follow_ups: list[str] = Field(default_factory=list, alias="followUps")
