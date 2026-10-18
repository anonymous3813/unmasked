"""The on-page agent answers from the product in front of the shopper."""

from backend.app.services.shop.agent import answer_question


def test_the_agent_reply_comes_from_the_model():
    def complete(prompt: str) -> str:
        assert "Can I return these?" in prompt
        assert "30 days" in prompt
        return '{"answer": "You can return unworn items within 30 days."}'

    reply = answer_question(
        "Can I return these?",
        title="Tree Runner",
        page_text="Men's Tree Runner",
        notes=[{"title": "Return limit", "message": "Unworn items can be returned within 30 days."}],
        complete=complete,
    )

    assert reply == "You can return unworn items within 30 days."


def test_a_return_question_uses_the_page_when_the_model_is_unavailable():
    def complete(_prompt: str) -> str:
        raise RuntimeError("Gemini daily quota is used")

    reply = answer_question(
        "what is the return policy",
        notes=[{"title": "Returns", "message": "15-day buyer protection applies to this order."}],
        complete=complete,
    )

    assert reply == "15-day buyer protection applies to this order."
