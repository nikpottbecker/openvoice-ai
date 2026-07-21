from __future__ import annotations

from html import escape

from phone_agent.models import AgentState


def classify_subject(state: AgentState) -> str:
    text = f"{state.intent} {state.summary} {' '.join(t.get('content', '') for t in state.transcript)}".lower()
    if any(word in text for word in ("presse", "press", "journalist")):
        return "Vielen Dank fuer Ihre Presseanfrage"
    if state.intent == "appointment" or "termin" in text:
        return "Terminbestaetigung"
    return "Vielen Dank fuer Ihre Anfrage"


def build_internal_note(state: AgentState) -> str:
    appointment = state.appointment
    lines = [
        f"Call-ID: {state.call_id}",
        f"Telefonnummer: {state.caller_id}",
        f"Name: {state.caller_name or appointment.name or 'offen'}",
        f"Intent: {state.intent}",
        f"Termin: {appointment.date or 'offen'} {appointment.time or ''}".strip(),
        f"Thema: {appointment.topic or 'offen'}",
        f"Rueckrufnummer: {appointment.phone or state.caller_id or 'offen'}",
        "",
        "Zusammenfassung:",
        state.summary or "Keine Zusammenfassung vorhanden.",
        "",
        "Transkript:",
    ]
    for entry in state.transcript:
        role = entry.get("role", "")
        content = entry.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_draft_body(state: AgentState) -> str:
    appointment = state.appointment
    greeting = f"Hallo {appointment.name}," if appointment.name else "Hallo,"
    if state.intent == "appointment":
        details = []
        if appointment.date:
            details.append(appointment.date)
        if appointment.time:
            details.append(appointment.time)
        if appointment.topic:
            details.append(f"zum Thema {appointment.topic}")
        when = " ".join(details).strip()
        return (
            f"{greeting}\n\n"
            f"vielen Dank fuer Ihren Anruf. Wir haben Ihre Terminanfrage {when} aufgenommen.\n"
            "Wir melden uns zur Rueckmeldung bei Ihnen.\n\n"
            "Viele Gruesse\nOpenVoice AI"
        )
    return (
        f"{greeting}\n\n"
        "vielen Dank fuer Ihre Anfrage. Wir haben Ihr Anliegen aufgenommen.\n"
        "Wir melden uns zur Rueckmeldung bei Ihnen.\n\n"
        "Viele Gruesse\nOpenVoice AI"
    )


def build_internal_summary_html(state: AgentState, errors: list[str], dashboard_url: str) -> str:
    appointment = state.appointment
    transcript = "\n".join(f"{item.get('role', '')}: {item.get('content', '')}" for item in state.transcript)
    callback = "Ja" if state.intent == "callback" or appointment.phone else "Nein"
    rows = [
        ("Telefonnummer", state.caller_id or "offen"),
        ("Erkannter Name", state.caller_name or appointment.name or "offen"),
        ("Intent", state.intent or "unknown"),
        ("E-Mail", _find_email(transcript) or "nicht vorhanden"),
        ("Termin", _appointment_line(state)),
        ("Rueckruf gewuenscht", callback),
        ("Call-ID", state.call_id),
    ]
    error_block = ""
    if errors:
        error_items = "".join(f"<li>{escape(error)}</li>" for error in errors)
        error_block = f"""
          <section class="card error">
            <h2>Fehler</h2>
            <ul>{error_items}</ul>
          </section>
        """
    return _email_shell(
        title="Neuer Telefonanruf",
        eyebrow="OpenVoice AI",
        dashboard_url=dashboard_url,
        intro="Ein neuer Anruf wurde verarbeitet. Die wichtigsten Daten sind hier kompakt zusammengefasst.",
        content=f"""
          {_summary_table(rows)}
          <section class="card">
            <h2>Zusammenfassung</h2>
            <p>{escape(state.summary or 'Keine Zusammenfassung vorhanden.')}</p>
          </section>
          <section class="card">
            <h2>Transkript</h2>
            <pre>{escape(transcript or 'Kein Transkript vorhanden.')}</pre>
          </section>
          {error_block}
        """,
    )


def build_draft_html_body(state: AgentState, plain_body: str, dashboard_url: str) -> str:
    appointment = state.appointment
    rows = [
        ("Name", appointment.name or state.caller_name or "offen"),
        ("Datum", appointment.date or "offen"),
        ("Uhrzeit", appointment.time or "offen"),
        ("Thema", appointment.topic or state.summary or "offen"),
    ]
    return _email_shell(
        title=classify_subject(state),
        eyebrow="Telefonanfrage",
        dashboard_url=dashboard_url,
        intro="Vielen Dank fuer Ihren Anruf. Wir haben Ihr Anliegen aufgenommen.",
        content=f"""
          <section class="card">
            <h2>Nachricht</h2>
            {_paragraphs(plain_body)}
          </section>
          <section class="card">
            <h2>Uebersicht</h2>
            {_summary_table(rows)}
          </section>
        """,
    )


def build_manual_email_html(subject: str, body: str, dashboard_url: str) -> str:
    return _email_shell(
        title=subject,
        eyebrow="OpenVoice AI",
        dashboard_url=dashboard_url,
        intro="Diese E-Mail wurde manuell ueber das geschuetzte Dashboard freigegeben.",
        content=f"""
          <section class="card">
            <h2>Nachricht</h2>
            {_paragraphs(body)}
          </section>
        """,
    )


def _email_shell(title: str, eyebrow: str, dashboard_url: str, intro: str, content: str) -> str:
    safe_url = escape(dashboard_url, quote=True)
    safe_title = escape(title)
    return f"""<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>
      body {{ margin:0; background:#f4f4f5; color:#18181b; font-family:Arial, Helvetica, sans-serif; }}
      .wrap {{ max-width:760px; margin:0 auto; padding:28px 16px; }}
      .hero {{ background:#111827; color:#fff; border-radius:18px; padding:28px; }}
      .eyebrow {{ margin:0 0 8px; color:#a7f3d0; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
      h1 {{ margin:0; font-size:26px; line-height:1.2; }}
      .intro {{ margin:14px 0 0; color:#d1d5db; line-height:1.55; }}
      .card {{ background:#fff; border:1px solid #e4e4e7; border-radius:14px; padding:20px; margin-top:16px; }}
      .card h2 {{ margin:0 0 12px; font-size:16px; }}
      table {{ width:100%; border-collapse:collapse; }}
      td {{ padding:10px 0; border-top:1px solid #eee; vertical-align:top; }}
      td:first-child {{ width:34%; color:#71717a; }}
      p {{ line-height:1.6; }}
      pre {{ white-space:pre-wrap; font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:13px; line-height:1.5; }}
      .button {{ display:inline-block; margin-top:18px; background:#2563eb; color:#fff !important; text-decoration:none; padding:12px 16px; border-radius:10px; font-weight:700; }}
      .footer {{ color:#71717a; font-size:12px; margin-top:18px; line-height:1.5; }}
      .error {{ border-color:#fecaca; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="hero">
        <p class="eyebrow">{escape(eyebrow)}</p>
        <h1>{safe_title}</h1>
        <p class="intro">{escape(intro)}</p>
        <a class="button" href="{safe_url}">Dashboard oeffnen</a>
      </div>
      {content}
      <p class="footer">OpenVoice AI hat diese E-Mail automatisch vorbereitet. API-Schluessel und Passwoerter werden niemals in E-Mails angezeigt.</p>
    </div>
  </body>
</html>"""


def _summary_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<tr><td>{escape(label)}</td><td><strong>{escape(value)}</strong></td></tr>" for label, value in rows)
    return f"<table>{body}</table>"


def _paragraphs(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs) or "<p></p>"


def _appointment_line(state: AgentState) -> str:
    appt = state.appointment
    parts = [appt.date or "offen"]
    if appt.time:
        parts.append(appt.time)
    if appt.topic:
        parts.append(f"wegen {appt.topic}")
    return " ".join(parts)


def _find_email(text: str) -> str | None:
    import re

    match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    return match.group(0) if match else None
