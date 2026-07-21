import smtplib
from email.message import EmailMessage

from phone_agent.config import get_settings


def test_smtp_login() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        return False, "SMTP not configured"
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
        return True, "SMTP login ok"
    except Exception as exc:
        return False, str(exc)


def send_message(to_addr: str, subject: str, body: str, html_body: str | None = None) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
