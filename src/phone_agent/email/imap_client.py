import imaplib

from phone_agent.config import get_settings


def test_imap_login() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.imap_host or not settings.imap_username or not settings.imap_password:
        return False, "IMAP not configured"
    try:
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=15) as imap:
            imap.login(settings.imap_username, settings.imap_password)
            imap.logout()
        return True, "IMAP login ok"
    except Exception as exc:
        return False, str(exc)
