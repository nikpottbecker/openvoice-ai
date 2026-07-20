import pytest

from phone_agent.agent import PhoneAgent, handle_turn_sync
from phone_agent.models import LLMResult


APPOINTMENT_STARTS = [
    "Ich brauche einen Termin",
    "Ich moechte morgen um 15 Uhr einen Termin machen",
    "Termin fuer Fotoshooting bitte",
    "Kann ich einen Rueckruf fuer einen Termin bekommen",
    "Naechste Woche brauche ich ein Shooting",
    "Ich will ein Foto Shooting buchen",
    "Haben Sie morgen um drei Uhr Zeit",
    "Ich brauche einen Termin fuer ein Video",
    "Kann man bei Nik einen Termin machen",
    "Ich haette gerne einen Termin",
    "Ich hätte gerne einen Termin",
]

NAMES = [
    "Nik Pottbecker",
    "Schmitz",
    "Mueller",
    "Svenja Krause",
    "Ahmed Yilmaz",
    "Lea Hoffmann",
    "Mia Schneider",
    "Jonas Becker",
    "Herr Wagner",
    "Frau Neumann",
]

DATE_TIMES = [
    "morgen um 15 Uhr",
    "Mittwoch um 10",
    "naechsten Dienstag nachmittags",
    "heute um 16 Uhr 30",
    "am 12.7. um 14 Uhr",
    "Freitag Vormittag",
    "uebermorgen um 9",
    "naechste Woche Mittwoch 15 Uhr",
    "am Montag gegen drei",
    "Donnerstag um elf",
    "Mittwoch um halb drei",
    "Freitag viertel nach drei",
    "Montag viertel vor vier",
]

TOPICS = [
    "Fotoshooting",
    "Eventfotografie",
    "Livestream",
    "Presseanfrage",
    "Video fuer eine Veranstaltung",
    "Motorsport Bilder",
    "Bildlizenz",
    "Rueckruf",
    "Bewerbungsfotos",
    "Medienproduktion",
]

PHONES = [
    "015735703185",
    "0176 12345678",
    "+49 1573 5703185",
    "02831 12345",
    "0171 2223334",
    "null eins sieben sechs eins zwei drei vier",
    "0151 123 456",
    "0211 55555",
    "0160 4444444",
    "0172 9876543",
    "null eins sieben sechs fünf vier drei zwei",
    "null eins zwo drei vier fünf sechs",
    "null eins sieben sechs fuenfzehn dreizehn",
    "null eins fuenf sieben siebzehn elf",
    "plus vier neun eins fuenf sieben drei",
]


@pytest.mark.parametrize("text", APPOINTMENT_STARTS)
def test_appointment_start_never_repeats_generic_help_question(text: str) -> None:
    agent = PhoneAgent(call_id="test-call", caller_id="anonymous")

    reply = handle_turn_sync(agent, text).reply.lower()

    assert "wie kann ich" not in reply
    assert agent.state.intent == "appointment"
    assert agent.state.expected_slot in {"name", "appointment_confirm"}


@pytest.mark.parametrize("name", NAMES)
def test_name_slot_accepts_any_non_empty_text(name: str) -> None:
    agent = PhoneAgent(call_id=f"test-name-{name}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin fuer ein Fotoshooting machen")

    result = handle_turn_sync(agent, name)

    assert agent.state.appointment.name == name
    assert agent.state.expected_slot != "name"
    assert "name" not in result.reply.lower()


@pytest.mark.parametrize(
    ("spoken_name", "expected_name"),
    [
        ("ich heiße Tim Becker", "Tim Becker"),
        ("mein Vorname ist Laura", "Laura"),
        ("der Name ist Schmitz", "Schmitz"),
        ("ich bin der Nik", "Nik"),
        ("ich bin die Lea", "Lea"),
    ],
)
def test_name_slot_removes_common_intro_phrases(spoken_name: str, expected_name: str) -> None:
    agent = PhoneAgent(call_id=f"test-name-clean-{spoken_name}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin fuer ein Fotoshooting machen")

    handle_turn_sync(agent, spoken_name)

    assert agent.state.appointment.name == expected_name


def test_name_slot_does_not_store_filler_as_name() -> None:
    agent = PhoneAgent(call_id="test-name-filler", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")

    result = handle_turn_sync(agent, "ähm")

    assert agent.state.appointment.name is None
    assert agent.state.expected_slot == "name"
    assert "name" in result.reply.lower()


def test_name_correction_stores_corrected_name_only() -> None:
    agent = PhoneAgent(call_id="test-name-correction", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")

    result = handle_turn_sync(agent, "nicht Mueller sondern Schmidt")

    assert agent.state.appointment.name == "schmidt"
    assert agent.state.caller_name == "schmidt"
    assert agent.state.expected_slot == "date_time"
    assert "termin" in result.reply.lower()


def test_name_slot_extracts_name_and_prefills_embedded_details() -> None:
    agent = PhoneAgent(call_id="test-name-with-details", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")

    result = handle_turn_sync(agent, "Nik Pottbecker morgen um 15 Uhr Fotoshooting")

    assert agent.state.appointment.name == "nik pottbecker"
    assert agent.state.appointment.date == "morgen"
    assert agent.state.appointment.time == "15:00"
    assert agent.state.appointment.topic == "Fotoshooting"
    assert agent.state.expected_slot == "phone"
    assert "telefon" in result.reply.lower()


def test_name_slot_does_not_store_appointment_details_as_name() -> None:
    agent = PhoneAgent(call_id="test-name-slot-no-name-details", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")

    result = handle_turn_sync(agent, "morgen um 15 Uhr Fotoshooting")

    assert agent.state.appointment.name is None
    assert agent.state.expected_slot == "name"
    assert "name" in result.reply.lower()


@pytest.mark.parametrize("date_time", DATE_TIMES)
def test_date_time_slot_advances(date_time: str) -> None:
    agent = PhoneAgent(call_id=f"test-date-{date_time}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    result = handle_turn_sync(agent, date_time)

    assert agent.state.appointment.date
    assert agent.state.appointment.time
    assert agent.state.expected_slot == "topic"
    assert "worum" in result.reply.lower()


def test_date_time_slot_prefills_topic_when_in_same_answer() -> None:
    agent = PhoneAgent(call_id="test-date-time-with-topic", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    result = handle_turn_sync(agent, "morgen um 15 Uhr Fotoshooting")

    assert agent.state.appointment.date == "morgen"
    assert agent.state.appointment.time == "15:00"
    assert agent.state.appointment.topic == "Fotoshooting"
    assert agent.state.expected_slot == "phone"
    assert "telefon" in result.reply.lower()


def test_date_only_keeps_date_time_slot_and_asks_for_time() -> None:
    agent = PhoneAgent(call_id="test-date-only", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    result = handle_turn_sync(agent, "Mittwoch")

    assert agent.state.appointment.date == "mittwoch"
    assert agent.state.appointment.time is None
    assert agent.state.expected_slot == "date_time"
    assert "uhrzeit" in result.reply.lower()


def test_time_after_date_completes_date_time_without_overwriting_date() -> None:
    agent = PhoneAgent(call_id="test-time-after-date", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "Mittwoch")

    result = handle_turn_sync(agent, "15 Uhr")

    assert agent.state.appointment.date == "mittwoch"
    assert agent.state.appointment.time == "15:00"
    assert agent.state.expected_slot == "topic"
    assert "worum" in result.reply.lower()


def test_date_time_correction_replaces_previous_date() -> None:
    agent = PhoneAgent(call_id="test-date-correction", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "Mittwoch")

    result = handle_turn_sync(agent, "nicht Mittwoch, Donnerstag um 15 Uhr")

    assert agent.state.appointment.date == "donnerstag"
    assert agent.state.appointment.time == "15:00"
    assert agent.state.expected_slot == "topic"
    assert "worum" in result.reply.lower()


def test_date_time_correction_with_sondern_replaces_previous_date() -> None:
    agent = PhoneAgent(call_id="test-date-correction-sondern", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "Mittwoch")

    handle_turn_sync(agent, "nicht Mittwoch sondern Freitag um 10")

    assert agent.state.appointment.date == "freitag"
    assert agent.state.appointment.time == "10:00"


def test_time_only_keeps_date_time_slot_and_asks_for_day() -> None:
    agent = PhoneAgent(call_id="test-time-only", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    result = handle_turn_sync(agent, "15 Uhr")

    assert agent.state.appointment.date is None
    assert agent.state.appointment.time == "15:00"
    assert agent.state.expected_slot == "date_time"
    assert "tag" in result.reply.lower()


def test_date_after_time_completes_date_time_without_overwriting_time() -> None:
    agent = PhoneAgent(call_id="test-date-after-time", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "15 Uhr")

    result = handle_turn_sync(agent, "Mittwoch")

    assert agent.state.appointment.date == "mittwoch"
    assert agent.state.appointment.time == "15:00"
    assert agent.state.expected_slot == "topic"
    assert "worum" in result.reply.lower()


def test_unclear_date_time_does_not_store_as_date_on_first_failure() -> None:
    agent = PhoneAgent(call_id="test-unclear-date-time", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    result = handle_turn_sync(agent, "weiss ich nicht")

    assert agent.state.appointment.date is None
    assert agent.state.appointment.time is None
    assert agent.state.expected_slot == "date_time"
    assert "wann" in result.reply.lower()


def test_second_unclear_date_time_is_saved_as_note_and_advances() -> None:
    agent = PhoneAgent(call_id="test-second-unclear-date-time", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "weiss ich nicht")

    result = handle_turn_sync(agent, "keine ahnung")

    assert agent.state.appointment.date == "keine ahnung"
    assert agent.state.expected_slot == "date_time"
    assert "uhrzeit" in result.reply.lower()


def test_prefilled_date_still_asks_time_after_name() -> None:
    agent = PhoneAgent(call_id="test-prefilled-date-only", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte morgen einen Termin")

    result = handle_turn_sync(agent, "Nik Pottbecker")

    assert agent.state.appointment.date == "morgen"
    assert agent.state.appointment.time is None
    assert agent.state.expected_slot == "date_time"
    assert "uhrzeit" in result.reply.lower()


@pytest.mark.parametrize("topic", TOPICS)
def test_topic_slot_advances_to_phone(topic: str) -> None:
    agent = PhoneAgent(call_id=f"test-topic-{topic}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")

    result = handle_turn_sync(agent, topic)

    assert agent.state.appointment.topic == topic
    assert agent.state.expected_slot == "phone"
    assert "nummer" in result.reply.lower()


def test_topic_correction_stores_corrected_topic_only() -> None:
    agent = PhoneAgent(call_id="test-topic-correction", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")

    result = handle_turn_sync(agent, "nicht Fotoshooting sondern Video")

    assert agent.state.appointment.topic == "video"
    assert agent.state.expected_slot == "phone"
    assert "nummer" in result.reply.lower()


def test_topic_correction_with_comma_stores_corrected_topic_only() -> None:
    agent = PhoneAgent(call_id="test-topic-correction-comma", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")

    handle_turn_sync(agent, "nicht livestream, presseanfrage")

    assert agent.state.appointment.topic == "presseanfrage"


def test_topic_slot_extracts_phone_from_same_answer() -> None:
    agent = PhoneAgent(call_id="test-topic-with-phone", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")

    result = handle_turn_sync(agent, "Fotoshooting 0176 12345678")

    assert agent.state.appointment.topic == "fotoshooting"
    assert agent.state.appointment.phone == "017612345678"
    assert agent.state.expected_slot == "confirmed"
    assert "passt" in result.reply.lower()


def test_topic_slot_extracts_spoken_phone_from_same_answer() -> None:
    agent = PhoneAgent(call_id="test-topic-with-spoken-phone", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")

    handle_turn_sync(agent, "Video null eins sieben sechs fuenfzehn dreizehn")

    assert agent.state.appointment.topic == "video"
    assert agent.state.appointment.phone == "01761513"
    assert agent.state.expected_slot == "confirmed"


@pytest.mark.parametrize("phone", PHONES)
def test_phone_slot_advances_to_confirmation(phone: str) -> None:
    agent = PhoneAgent(call_id=f"test-phone-{phone}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    result = handle_turn_sync(agent, phone)

    assert agent.state.appointment.phone
    assert agent.state.expected_slot == "confirmed"
    assert "passt" in result.reply.lower()


def test_phone_slot_rejects_non_phone_text_once() -> None:
    agent = PhoneAgent(call_id="test-phone-rejects-text", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    result = handle_turn_sync(agent, "das habe ich gerade nicht zur Hand")

    assert agent.state.appointment.phone is None
    assert agent.state.expected_slot == "phone"
    assert "nummer" in result.reply.lower()


def test_phone_slot_rejects_too_short_number_once() -> None:
    agent = PhoneAgent(call_id="test-phone-rejects-short-number", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    result = handle_turn_sync(agent, "123")

    assert agent.state.appointment.phone is None
    assert agent.state.expected_slot == "phone"
    assert "nummer" in result.reply.lower()


def test_phone_correction_accepts_corrected_number() -> None:
    agent = PhoneAgent(call_id="test-phone-correction", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    result = handle_turn_sync(agent, "nicht 12345 sondern 0176 12345678")

    assert agent.state.appointment.phone == "017612345678"
    assert agent.state.expected_slot == "confirmed"
    assert "passt" in result.reply.lower()


def test_phone_correction_with_comma_accepts_corrected_number() -> None:
    agent = PhoneAgent(call_id="test-phone-correction-comma", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    handle_turn_sync(agent, "nicht die alte, plus vier neun eins fuenf sieben drei")

    assert agent.state.appointment.phone == "+491573"
    assert agent.state.expected_slot == "confirmed"


@pytest.mark.parametrize("confirmation", ["ja", "passt", "genau", "okay", "richtig"])
def test_confirmation_ends_slot_flow(confirmation: str) -> None:
    agent = PhoneAgent(call_id=f"test-confirm-{confirmation}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")
    handle_turn_sync(agent, "015735703185")

    result = handle_turn_sync(agent, confirmation)

    assert agent.state.appointment.confirmed is True
    assert agent.state.expected_slot is None
    assert "weiter" in result.reply.lower()


@pytest.mark.parametrize("confirmation", ["jo", "jawohl", "klar", "stimmt", "doch", "nein doch"])
def test_colloquial_confirmation_ends_slot_flow(confirmation: str) -> None:
    agent = PhoneAgent(call_id=f"test-colloquial-confirm-{confirmation}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")
    handle_turn_sync(agent, "015735703185")

    handle_turn_sync(agent, confirmation)

    assert agent.state.appointment.confirmed is True
    assert agent.state.expected_slot is None


def test_unclear_confirmation_retries_once_then_takes_message() -> None:
    agent = PhoneAgent(call_id="test-unclear-confirmation", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")
    handle_turn_sync(agent, "015735703185")

    first = handle_turn_sync(agent, "vielleicht").reply
    second = handle_turn_sync(agent, "weiss ich nicht").reply

    assert agent.state.appointment.confirmed is False
    assert "passt" in first.lower()
    assert agent.state.expected_slot is None
    assert "weiter" in second.lower()


@pytest.mark.parametrize("negative", ["nein", "nee", "nö"])
def test_negative_confirmation_takes_note_without_loop(negative: str) -> None:
    agent = PhoneAgent(call_id=f"test-negative-confirmation-{negative}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")
    handle_turn_sync(agent, "015735703185")

    result = handle_turn_sync(agent, negative)

    assert agent.state.appointment.confirmed is False
    assert agent.state.expected_slot is None
    assert "notiz" in result.reply.lower()


def test_appointment_flow_asks_at_most_one_question_per_reply() -> None:
    agent = PhoneAgent(call_id="test-one-question", caller_id="anonymous")
    replies = [
        handle_turn_sync(agent, "Ich moechte einen Termin").reply,
        handle_turn_sync(agent, "Nik Pottbecker").reply,
        handle_turn_sync(agent, "morgen um 15 Uhr").reply,
        handle_turn_sync(agent, "Fotoshooting").reply,
        handle_turn_sync(agent, "015735703185").reply,
        handle_turn_sync(agent, "ja").reply,
    ]

    assert all(reply.count("?") <= 1 for reply in replies)


def test_standard_appointment_replies_stay_short() -> None:
    agent = PhoneAgent(call_id="test-short-standard-replies", caller_id="anonymous")
    replies = [
        handle_turn_sync(agent, "Ich moechte einen Termin").reply,
        handle_turn_sync(agent, "Nik Pottbecker").reply,
        handle_turn_sync(agent, "morgen um 15 Uhr").reply,
        handle_turn_sync(agent, "Fotoshooting").reply,
        handle_turn_sync(agent, "015735703185").reply,
        handle_turn_sync(agent, "ja").reply,
    ]

    assert max(len(reply) for reply in replies) <= 30


def test_force_appointment_flow_uses_fuzzy_detection_after_generic_llm_reply() -> None:
    agent = PhoneAgent(call_id="test-force-fuzzy", caller_id="anonymous")
    generic = LLMResult(reply="Wie kann ich Ihnen helfen?", intent="unknown")

    result = agent._force_appointment_flow(generic, "Ich haette gerne einen Thermin")

    assert result.intent == "appointment"
    assert agent.state.expected_slot == "name"
    assert "name" in result.reply.lower()


def test_negative_appointment_guess_clears_appointment_intent() -> None:
    agent = PhoneAgent(call_id="test-negative-appointment-guess", caller_id="anonymous")
    handle_turn_sync(agent, "morgen")

    result = handle_turn_sync(agent, "nein")

    assert result.intent == "unknown"
    assert agent.state.intent == "unknown"
    assert agent.state.expected_slot is None


def test_cancel_text_exits_active_appointment_slot_without_storing_name() -> None:
    agent = PhoneAgent(call_id="test-cancel-name-slot", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")

    result = handle_turn_sync(agent, "doch nicht")

    assert result.intent == "unknown"
    assert agent.state.intent == "unknown"
    assert agent.state.expected_slot is None
    assert agent.state.appointment.name is None
    assert "worum" in result.reply.lower()


def test_cancel_text_exits_phone_slot_without_storing_phone() -> None:
    agent = PhoneAgent(call_id="test-cancel-phone-slot", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")
    handle_turn_sync(agent, "morgen um 15 Uhr")
    handle_turn_sync(agent, "Fotoshooting")

    result = handle_turn_sync(agent, "abbrechen")

    assert result.intent == "unknown"
    assert agent.state.expected_slot is None
    assert agent.state.appointment.phone is None


def test_ambiguous_appointment_guess_uses_short_confirmation_question() -> None:
    agent = PhoneAgent(call_id="test-short-appointment-guess", caller_id="anonymous")

    result = handle_turn_sync(agent, "morgen")

    assert result.reply == "Geht es um einen Termin?"
    assert agent.state.expected_slot == "appointment_confirm"
    assert len(result.reply) < 30


def test_50_complete_simulated_appointment_calls_keep_state() -> None:
    starts = [
        "Ich moechte einen Termin",
        "Ich will einen Termin vereinbaren",
        "Ich brauche einen Termin",
        "Ich haette gerne einen Termin",
        "Kann ich einen Termin buchen",
    ]
    names = ["Nik Pottbecker", "Lea Hoffmann", "Ahmed Yilmaz", "Mia Schneider", "Jonas Becker"]
    date_times = [
        "morgen um 15 Uhr",
        "Mittwoch um 10",
        "Freitag Vormittag",
        "uebermorgen um 9",
        "Donnerstag um elf",
    ]
    topics = ["Fotoshooting", "Livestream", "Eventfotografie", "Video", "Bildlizenz"]
    phones = ["015735703185", "0176 12345678", "+49 1573 5703185", "02831 12345", "0172 9876543"]

    completed = 0
    for index in range(50):
        agent = PhoneAgent(call_id=f"sim-appointment-{index}", caller_id="anonymous")
        turns = [
            starts[index % len(starts)],
            names[index % len(names)],
            date_times[index % len(date_times)],
            topics[index % len(topics)],
            phones[index % len(phones)],
            "ja",
        ]
        replies = [handle_turn_sync(agent, text).reply for text in turns]

        assert agent.state.appointment.confirmed is True
        assert agent.state.expected_slot is None
        assert agent.state.appointment.name == turns[1]
        assert agent.state.appointment.topic == turns[3]
        assert agent.state.appointment.phone
        assert all("wie kann ich" not in reply.lower() for reply in replies)
        assert all(reply.count("?") <= 1 for reply in replies)
        completed += 1

    assert completed == 50


def test_prefilled_topic_skips_topic_question() -> None:
    agent = PhoneAgent(call_id="test-prefilled-topic", caller_id="anonymous")

    handle_turn_sync(agent, "Termin fuer Fotoshooting bitte")
    handle_turn_sync(agent, "Nik Pottbecker")
    result = handle_turn_sync(agent, "morgen um 15 Uhr")

    assert agent.state.appointment.topic == "Fotoshooting"
    assert agent.state.expected_slot == "phone"
    assert "nummer" in result.reply.lower()


def test_morgen_frueh_is_stored_as_time_of_day() -> None:
    agent = PhoneAgent(call_id="test-morgen-frueh", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    handle_turn_sync(agent, "morgen frueh")

    assert agent.state.appointment.date == "morgen"
    assert agent.state.appointment.time == "morgens"


@pytest.mark.parametrize(
    ("spoken", "expected_date", "expected_time"),
    [
        ("am 12.7. um 14 Uhr", "12.7", "14:00"),
        ("heute um 16 Uhr 30", "heute", "16:30"),
        ("morgen frueh zu telefonieren", "morgen", "morgens"),
        ("übermorgen um fünfzehn Uhr", "uebermorgen", "15:00"),
        ("Ã¼bermorgen um fÃ¼nfzehn Uhr", "uebermorgen", "15:00"),
        ("Freitag Vormittag", "freitag", "vormittags"),
        ("nächsten Dienstag nachmittags", "naechsten dienstag", "nachmittags"),
        ("am Montag gegen drei", "montag", "3:00"),
        ("Donnerstag um elf", "donnerstag", "11:00"),
        ("Mittwoch um halb drei", "mittwoch", "2:30"),
        ("Mittwoch um halb 3", "mittwoch", "2:30"),
        ("Freitag viertel nach drei", "freitag", "3:15"),
        ("Freitag viertel nach 3", "freitag", "3:15"),
        ("Montag viertel vor vier", "montag", "3:45"),
        ("Montag viertel drei", "montag", "2:15"),
        ("Montag dreiviertel drei", "montag", "2:45"),
        ("zwoelfter siebter um 14 Uhr", "12.7", "14:00"),
        ("fuenfzehnter Juli um zehn", "15.7", "10:00"),
        ("am zwoelften siebten um 14 Uhr", "12.7", "14:00"),
        ("am fuenfzehnten Juli um zehn", "15.7", "10:00"),
    ],
)
def test_date_time_parser_keeps_date_and_time_separate(
    spoken: str,
    expected_date: str,
    expected_time: str,
) -> None:
    agent = PhoneAgent(call_id=f"test-date-time-exact-{spoken}", caller_id="anonymous")
    handle_turn_sync(agent, "Ich moechte einen Termin")
    handle_turn_sync(agent, "Nik Pottbecker")

    handle_turn_sync(agent, spoken)

    assert agent.state.appointment.date == expected_date
    assert agent.state.appointment.time == expected_time


@pytest.mark.parametrize(
    "text",
    [
        "Ich brauche einen Rückruf",
        "Bitte zurückrufen",
        "Kann Nik mich wegen einem Termin zurückrufen",
    ],
)
def test_callback_umlaut_signals_are_detected(text: str) -> None:
    agent = PhoneAgent(call_id=f"test-callback-{text}", caller_id="anonymous")

    agent._apply_hard_intent_detection(text)

    assert agent.state.intent == "callback"
