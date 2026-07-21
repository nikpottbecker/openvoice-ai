import pytest

from phone_agent.menu import (
    HybridAction,
    HybridMenuSession,
    action_from_dtmf,
    action_from_speech,
    default_menu_config,
)
from phone_agent.models import AgentState
from phone_agent.simple_agi import agi_digit


def test_dtmf_and_speech_share_create_appointment_action() -> None:
    config = default_menu_config()

    assert action_from_dtmf("1", config) == HybridAction.CREATE_APPOINTMENT
    assert action_from_speech("Ich brauche einen Termin", config) == HybridAction.CREATE_APPOINTMENT


def test_default_menu_prompt_is_dtmf_first_and_offers_ai_agent() -> None:
    config = default_menu_config()

    assert config.prompt.startswith("Willkommen beim Telefonagenten von Nik Pottbecker")
    assert "Druecken Sie die 1 fuer einen Termin" in config.prompt
    assert "Druecken Sie die 2, um mit dem KI Agenten zu sprechen" in config.prompt
    assert "sagen" not in config.prompt.lower()
    assert "sprechen sie" not in config.prompt.lower()


def test_dtmf_two_opens_ai_agent_flow() -> None:
    state = AgentState(call_id="menu-ai-agent", caller_id="anonymous")
    menu = HybridMenuSession(state)

    result = menu.handle_dtmf("2")

    assert result.should_end_call is False
    assert result.reply == "Gerne. Worum geht es?"
    assert state.expected_slot is None
    assert menu.menu_level == "agent"


def test_speech_examples_map_to_expected_actions() -> None:
    config = default_menu_config()

    assert action_from_speech("Ich moechte meinen Termin verschieben.", config) == HybridAction.CHANGE_APPOINTMENT
    assert action_from_speech("Rufen Sie mich bitte zurueck.", config) == HybridAction.REQUEST_CALLBACK
    assert action_from_speech("Wie lange haben Sie heute geoeffnet?", config) == HybridAction.GET_INFORMATION


def test_unknown_dtmf_is_rejected_without_state_change() -> None:
    state = AgentState(call_id="menu-invalid", caller_id="anonymous")
    menu = HybridMenuSession(state)

    result = menu.handle_dtmf("x")

    assert result.should_end_call is False
    assert "nicht verfuegbar" in result.reply
    assert state.intent == "unknown"


def test_valid_input_resets_invalid_retry_counter() -> None:
    state = AgentState(call_id="menu-retry-reset", caller_id="anonymous")
    menu = HybridMenuSession(state)

    first_invalid = menu.handle_dtmf("x")
    valid = menu.handle_dtmf("1")
    second_invalid = menu.handle_slot_dtmf("8")

    assert first_invalid.should_end_call is False
    assert valid.should_end_call is False
    assert second_invalid is not None
    assert second_invalid.should_end_call is False
    assert "nicht verfuegbar" in second_invalid.reply


def test_two_consecutive_invalid_inputs_still_fallback() -> None:
    state = AgentState(call_id="menu-two-invalid", caller_id="anonymous")
    menu = HybridMenuSession(state)

    first = menu.handle_dtmf("x")
    second = menu.handle_dtmf("y")

    assert first.should_end_call is False
    assert second.should_end_call is True
    assert "Nik" in second.reply


def test_change_and_cancel_appointment_have_safe_message_flows() -> None:
    state = AgentState(call_id="menu-change-cancel", caller_id="anonymous")
    menu = HybridMenuSession(state)

    change = menu.handle_speech_action("Ich moechte meinen Termin aendern")
    assert "aendern" in change.reply
    assert state.expected_slot == "message"

    state = AgentState(call_id="menu-cancel", caller_id="anonymous")
    menu = HybridMenuSession(state)
    cancel = menu.handle_dtmf("3")

    assert "absagen" in cancel.reply
    assert state.expected_slot == "message"


def test_message_slot_finishes_without_llm() -> None:
    state = AgentState(call_id="menu-message", caller_id="anonymous")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("5")

    result = menu.handle_slot_speech("Bitte wegen dem Event morgen zurueckrufen.")

    assert result is not None
    assert result.should_end_call is True
    assert state.summary == "Bitte wegen dem Event morgen zurueckrufen."
    assert state.expected_slot is None


def test_change_appointment_message_finishes_without_llm() -> None:
    state = AgentState(call_id="menu-change-message", caller_id="anonymous")
    menu = HybridMenuSession(state)
    menu.handle_speech_action("Ich moechte meinen Termin verschieben")

    result = menu.handle_slot_speech("Nik Pottbecker, Termin Mittwoch bitte auf Freitag verschieben.")

    assert result is not None
    assert result.should_end_call is True
    assert "verschieben" in state.summary
    assert state.expected_slot is None


def test_callback_other_spoken_phone_finishes_without_llm() -> None:
    state = AgentState(call_id="menu-callback-phone", caller_id="anonymous")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("4")
    menu.handle_slot_dtmf("2")

    result = menu.handle_slot_speech("null eins sieben sechs fuenfzehn dreizehn")

    assert result is not None
    assert result.should_end_call is True
    assert state.summary == "Rueckrufnummer: 01761513"
    assert state.expected_slot is None


@pytest.mark.parametrize("confirmation", ["ja", "stimmt", "okay", "klar"])
def test_callback_spoken_confirmation_finishes_without_llm(confirmation: str) -> None:
    state = AgentState(call_id=f"menu-callback-confirm-{confirmation}", caller_id="015735703185")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("4")

    result = menu.handle_slot_speech(confirmation)

    assert result is not None
    assert result.should_end_call is True
    assert state.expected_slot is None


def test_dtmf_only_appointment_flow_reaches_confirmation() -> None:
    state = AgentState(call_id="menu-dtmf-appointment", caller_id="015735703185")
    menu = HybridMenuSession(state)

    assert menu.handle_dtmf("1").reply.startswith("Termin")
    assert menu.handle_slot_dtmf("3").reply.startswith("Wann")
    assert menu.handle_slot_dtmf("2").reply.startswith("Worum")
    result = menu.handle_slot_speech("Fotoshooting")

    assert result is not None
    assert state.appointment.date == "Mittwoch"
    assert state.appointment.time == "nachmittags"
    assert state.appointment.topic == "Fotoshooting"
    assert state.appointment.phone == "015735703185"
    assert state.expected_slot == "confirmed"
    assert "Bestaetigen" in result.reply


def test_dtmf_confirmation_completes_appointment() -> None:
    state = AgentState(call_id="menu-confirm", caller_id="015735703185")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("1")
    menu.handle_slot_dtmf("1")
    menu.handle_slot_dtmf("3")
    menu.handle_slot_speech("Video")

    result = menu.handle_slot_dtmf("1")

    assert result.should_end_call is True
    assert state.appointment.confirmed is True
    assert state.expected_slot is None


def test_hybrid_flow_accepts_spoken_confirmation_after_dtmf_topic() -> None:
    state = AgentState(call_id="menu-spoken-confirm", caller_id="015735703185")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("1")
    menu.handle_slot_dtmf("3")
    menu.handle_slot_dtmf("2")
    menu.handle_slot_speech("Foto")

    result = menu.handle_slot_speech("ja")

    assert result is not None
    assert result.should_end_call is True
    assert state.appointment.confirmed is True
    assert state.expected_slot is None


def test_speech_day_and_part_work_inside_dtmf_flow() -> None:
    state = AgentState(call_id="menu-mixed", caller_id="anonymous")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("1")

    assert menu.handle_slot_speech("Freitag") is not None
    assert menu.handle_slot_speech("vormittags") is not None

    assert state.appointment.date == "Freitag"
    assert state.appointment.time == "vormittags"
    assert state.expected_slot == "appointment_topic"


def test_speech_day_with_part_skips_extra_question_inside_dtmf_flow() -> None:
    state = AgentState(call_id="menu-mixed-combined-day-part", caller_id="anonymous")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("1")

    result = menu.handle_slot_speech("Freitag vormittags")

    assert result is not None
    assert state.appointment.date == "Freitag"
    assert state.appointment.time == "vormittags"
    assert state.expected_slot == "appointment_topic"
    assert "Worum" in result.reply


def test_speech_day_part_and_topic_jumps_to_confirmation_inside_dtmf_flow() -> None:
    state = AgentState(call_id="menu-mixed-combined-full", caller_id="015735703185")
    menu = HybridMenuSession(state)
    menu.handle_dtmf("1")

    result = menu.handle_slot_speech("Freitag vormittags Fotoshooting")

    assert result is not None
    assert state.appointment.date == "Freitag"
    assert state.appointment.time == "vormittags"
    assert state.appointment.topic == "Fotoshooting"
    assert state.appointment.phone == "015735703185"
    assert state.expected_slot == "confirmed"
    assert "Bestaetigen" in result.reply


def test_agi_digit_parses_asterisk_result_code() -> None:
    assert agi_digit("200 result=49 endpos=123") == "1"
    assert agi_digit("200 result=35") == "#"
    assert agi_digit("200 result=0") == ""
    assert agi_digit("510 Invalid command") == ""
