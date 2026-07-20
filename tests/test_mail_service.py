from phone_agent.email.mail_service import consent_for_external_mail, extract_email, normalize_spoken_email


def test_extract_email_from_regular_address() -> None:
    assert extract_email("Bitte an nik@example.com senden") == "nik@example.com"


def test_extract_email_from_spoken_german_address() -> None:
    text = "Bitte an nik punkt pottbecker at gmail punkt com senden"

    assert extract_email(text) == "nik.pottbecker@gmail.com"


def test_extract_email_from_spoken_symbols() -> None:
    text = "mail ist foto minus team klammeraffe beispiel punkt de"

    assert extract_email(text) == "foto-team@beispiel.de"


def test_normalize_spoken_email_keeps_sentence_readable() -> None:
    normalized = normalize_spoken_email("per e mail an test punkt name at example punkt com")

    assert "test.name@example.com" in normalized


def test_consent_for_external_mail_accepts_common_variants() -> None:
    assert consent_for_external_mail("Ja, bitte per e mail")
    assert consent_for_external_mail("Gerne eine Terminbestätigung")
