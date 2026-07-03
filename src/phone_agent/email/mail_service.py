import logging
import re
from datetime import datetime
from pathlib import Path

from phone_agent.config import get_settings
from phone_agent.models import AgentState

from .drafts import create_draft, mark_error, mark_sent
from .smtp_client import send_message
from .templates import build_draft_body, build_internal_note, classify_subject

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def handle_call_mail(state: AgentState, errors: list[str] | None = None) -> None:
    send_internal_summary(state, errors or [])
    create_external_draft_if_requested(state)


def create_call_email_draft(state: AgentState) -> int | None:
    create_external_draft_if_requested(state)
    return None


def send_internal_summary(state: AgentState, errors: list[str]) -> int | None:
    settings = get_settings()
    if not settings.internal_summary_to:
        logger.warning("internal_email_skipped call_id=%s reason=no_recipient", state.call_id)
        return None
    subject = f"Neuer Telefonanruf - {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    body = build_internal_summary_body(state, errors)
    draft_id = create_draft(
        state.call_id,
        settings.internal_summary_to,
        subject,
        body,
        build_internal_note(state),
        audience="internal",
        status="queued",
    )
    try:
        send_message(settings.internal_summary_to, subject, body)
        mark_sent(draft_id)
        logger.info("internal_email_sent call_id=%s draft_id=%s recipient=%s", state.call_id, draft_id, settings.internal_summary_to)
    except Exception as exc:
        mark_error(draft_id, str(exc))
        logger.exception("internal_email_failed call_id=%s draft_id=%s", state.call_id, draft_id)
    return draft_id


def create_external_draft_if_requested(state: AgentState) -> int | None:
    transcript_text = _transcript_text(state)
    email = extract_email(transcript_text)
    if not email:
        logger.info("external_email_draft_skipped call_id=%s reason=no_email", state.call_id)
        return None
    if not consent_for_external_mail(transcript_text):
        logger.info("external_email_draft_skipped call_id=%s reason=no_consent", state.call_id)
        return None
    subject = classify_subject(state)
    body = build_draft_body(state)
    internal_note = build_internal_note(state)
    draft_id = create_draft(state.call_id, email, subject, body, internal_note, audience="external", status="draft")
    logger.info("external_email_draft_created call_id=%s draft_id=%s recipient=%s subject=%s", state.call_id, draft_id, email, subject)
    return draft_id


def build_internal_summary_body(state: AgentState, errors: list[str]) -> str:
    settings = get_settings()
    appointment = state.appointment
    transcript = _transcript_text(state) or "Kein Transkript vorhanden."
    email = extract_email(transcript) or "nicht vorhanden"
    audio = _latest_audio_path(state.call_id) or "nicht vorhanden"
    dashboard = settings.dashboard_public_url or "lokal: http://127.0.0.1:8088"
    callback = "ja" if state.intent == "callback" or appointment.phone else "nein"
    lines = [
        f"Telefonnummer: {state.caller_id}",
        f"Erkannter Name: {state.caller_name or appointment.name or 'offen'}",
        f"E-Mail: {email}",
        "",
        "Zusammenfassung:",
        state.summary or "Keine Zusammenfassung vorhanden.",
        "",
        "Vollstaendiges Transkript:",
        transcript,
        "",
        "Erkannte Termine:",
        f"Name: {appointment.name or 'offen'}",
        f"Datum: {appointment.date or 'offen'}",
        f"Uhrzeit: {appointment.time or 'offen'}",
        f"Thema: {appointment.topic or 'offen'}",
        f"Telefon: {appointment.phone or 'offen'}",
        f"Bestaetigt: {'ja' if appointment.confirmed else 'nein'}",
        "",
        f"Rueckruf gewuenscht: {callback}",
        "Dauer: siehe Dashboard/Logs",
        f"Verwendetes KI-Modell: {settings.llm_provider} / {settings.nvidia_model}",
        f"Dashboard-Link: {dashboard}",
        f"Call-ID: {state.call_id}",
        f"Aufnahme: {audio}",
    ]
    if errors:
        lines.extend(["", "Fehler:", *errors])
    return "\n".join(lines)


def extract_email(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def consent_for_external_mail(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("ja", "gerne", "bitte", "zusammenfassung", "terminbestaetigung", "terminbestätigung", "per e-mail", "per email"))


def _transcript_text(state: AgentState) -> str:
    return "\n".join(f"{item.get('role', '')}: {item.get('content', '')}" for item in state.transcript)


def _latest_audio_path(call_id: str) -> str | None:
    recordings_dir = get_settings().recordings_dir
    paths = sorted(recordings_dir.glob(f"{call_id}-*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(paths[0]) if paths else None
