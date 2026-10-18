"""Shared phone and message profile for the shopper's agent."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ContactPurpose(str, Enum):
    """Why the shopper and the agent are in contact.

    The phone number and message thread are shared. Fine-print updates and
    later claim questions use different contexts on that same profile.
    """

    FINE_PRINT = "fine_print"
    CLAIM_VALIDATION = "claim_validation"


class MessageRole(str, Enum):
    """Who sent one message in the agent thread."""

    USER = "user"
    AGENT = "agent"


class FinePrintOrderContext(BaseModel):
    """Latest fine-print facts stored for one order."""

    price: str | None = None
    delivery: str | None = None
    specifications: list[str] = Field(default_factory=list)
    policies: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime


class PastOrder(BaseModel):
    """An order the shopper can open from the agent profile."""

    order_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    product_url: HttpUrl
    ordered_at: datetime
    store: str = ""
    price: str = ""
    environment_score: int | None = None
    materials: str = ""
    delivery_status: str = "Placed"
    notified_status: str = ""
    delivery_date: datetime | None = None
    notified_delivery_date: str = ""
    fine_print: FinePrintOrderContext | None = None


class AgentMessage(BaseModel):
    """One message on the shared phone and message thread."""

    role: MessageRole
    body: str = Field(min_length=1)
    purpose: ContactPurpose
    created_at: datetime
    order_id: str | None = None


class AgentCall(BaseModel):
    """A call the agent places to read a fine-print update."""

    phone_number: str = Field(min_length=1)
    purpose: ContactPurpose
    summary: str = Field(min_length=1)
    created_at: datetime


class AgentProfile(BaseModel):
    """The shopper's phone number, message thread, orders, and calls."""

    user_id: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    messages: list[AgentMessage] = Field(default_factory=list)
    orders: list[PastOrder] = Field(default_factory=list)
    calls: list[AgentCall] = Field(default_factory=list)
