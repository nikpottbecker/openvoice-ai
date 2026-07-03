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
