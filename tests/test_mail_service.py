from email.message import EmailMessage

from phone_agent.email.mail_service import consent_for_external_mail, dashboard_url, extract_email, normalize_spoken_email
from phone_agent.email.smtp_client import send_message
from phone_agent.email.templates import build_manual_email_html


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
    assert consent_for_external_mail("Gerne eine Terminbestaetigung")


def test_manual_email_html_contains_dashboard_link() -> None:
    html = build_manual_email_html("Test", "Hallo\n\nWelt", "https://agent.example/")

    assert "https://agent.example/" in html
    assert "Dashboard oeffnen" in html
    assert "Hallo" in html


def test_send_message_adds_html_alternative(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_FROM", "team@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "team@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    from phone_agent.config import get_settings

    get_settings.cache_clear()
    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("phone_agent.email.smtp_client.smtplib.SMTP", FakeSMTP)

    send_message("nik@example.com", "Betreff", "Text", html_body="<p>Text</p>")

    assert sent
    assert sent[0].is_multipart()
    assert sent[0].get_body(("html",)).get_content().strip() == "<p>Text</p>"


def test_dashboard_url_uses_configured_public_url(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "https://agent.example")
    from phone_agent.config import get_settings

    get_settings.cache_clear()

    assert dashboard_url() == "https://agent.example/"
