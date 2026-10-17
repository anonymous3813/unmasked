"""Phone and message profile shared by later agent contact purposes."""

from datetime import datetime, timezone

from backend.app.models.agent import (
    AgentCall,
    AgentMessage,
    AgentProfile,
    ContactPurpose,
    MessageRole,
    PastOrder,
)

_CLAIM_REPLY = (
    "Your question is saved on this phone and message thread. "
    "Claim questions use this same profile with a separate context."
)


class AgentContact:
    """Keep one phone number and message thread per shopper.

    Fine-print monitoring registers an answerer for product and order
    questions. Claim validation can register its own answerer later.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._answerers: dict[ContactPurpose, object] = {}

    def open_profile(self, user_id: str, phone_number: str) -> AgentProfile:
        """Create the shopper's phone profile, or return the one already open."""
        profile = self._profiles.get(user_id)
        if profile is None:
            profile = AgentProfile(user_id=user_id, phone_number=phone_number)
            self._profiles[user_id] = profile
            return profile
        profile.phone_number = phone_number
        return profile

    def profile(self, user_id: str) -> AgentProfile:
        """Return the shopper's phone and message profile."""
        return self._profiles[user_id]

    def past_orders(self, user_id: str) -> list[PastOrder]:
        """Return orders the shopper can review in the agent profile."""
        return list(self.profile(user_id).orders)

    def calls(self, user_id: str) -> list[AgentCall]:
        """Return calls placed to the shopper's phone."""
        return list(self.profile(user_id).calls)

    def register_answerer(self, purpose: ContactPurpose, answerer) -> None:
        """Attach the context used to answer questions for one contact purpose."""
        self._answerers[purpose] = answerer

    def add_order(self, user_id: str, order: PastOrder) -> None:
        """Save an order on the shopper's profile."""
        self.profile(user_id).orders.append(order)

    def record_message(
        self,
        user_id: str,
        role: MessageRole,
        body: str,
        purpose: ContactPurpose,
        order_id: str | None = None,
    ) -> AgentMessage:
        """Append one message to the shopper's thread."""
        return self._add_message(user_id, role, body, purpose, order_id)

    def place_call(self, user_id: str, purpose: ContactPurpose, summary: str) -> AgentCall:
        """Queue a call and record what the agent will say."""
        profile = self.profile(user_id)
        call = AgentCall(
            phone_number=profile.phone_number,
            purpose=purpose,
            summary=summary,
            created_at=datetime.now(timezone.utc),
        )
        profile.calls.append(call)
        self._add_message(user_id, MessageRole.AGENT, summary, purpose)
        return call

    def ask(
        self,
        user_id: str,
        question: str,
        purpose: ContactPurpose = ContactPurpose.FINE_PRINT,
    ) -> AgentMessage:
        """Store a shopper question and answer it from that purpose's context."""
        self._add_message(user_id, MessageRole.USER, question, purpose)
        answerer = self._answerers.get(purpose)
        if answerer is not None:
            body = answerer(self.profile(user_id), question)
        elif purpose is ContactPurpose.CLAIM_VALIDATION:
            body = _CLAIM_REPLY
        else:
            body = "Your question is saved on this phone and message thread."
        return self._add_message(user_id, MessageRole.AGENT, body, purpose)

    def _add_message(
        self,
        user_id: str,
        role: MessageRole,
        body: str,
        purpose: ContactPurpose,
        order_id: str | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            role=role,
            body=body,
            purpose=purpose,
            created_at=datetime.now(timezone.utc),
            order_id=order_id,
        )
        self.profile(user_id).messages.append(message)
        return message
