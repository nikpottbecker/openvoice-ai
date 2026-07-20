from phone_agent.llm import _infer_intent
from phone_agent.models import LLMResult


def test_infer_intent_normalizes_callback_umlaut() -> None:
    result = _infer_intent(LLMResult(reply="Ich notiere das."), "Bitte zurueckrufen")

    assert result.intent == "callback"


def test_infer_intent_replaces_generic_help_reply_for_appointment() -> None:
    result = _infer_intent(
        LLMResult(reply="Wie kann ich Ihnen helfen?", intent="appointment"),
        "Ich moechte einen Termin",
    )

    assert result.reply == "Gerne. Wie ist Ihr Name?"
