import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from phone_agent.config import get_settings, load_runtime_settings, save_runtime_settings
from phone_agent.email.drafts import delete_draft, get_draft, list_drafts, mark_error, mark_sent, update_draft
from phone_agent.email.smtp_client import send_message
from phone_agent.menu import HybridAction, default_menu_config, load_menu_config
from phone_agent.tts import synthesize_with_config
from phone_agent.tts_config import TTSConfig, available_tts_voices, load_tts_config, save_tts_config, validate_tts_config


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="OpenVoice AI Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
logger = logging.getLogger("phone_agent.dashboard")


def _db_path() -> Path:
    return get_settings().app_base_dir / "dashboard" / "dashboard.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "create table if not exists call_notes (call_id text primary key, status text, updated_at text)"
    )
    return conn


@app.middleware("http")
async def require_cloudflare_access(request: Request, call_next):
    if request.url.path in {"/healthz"}:
        return await call_next(request)
    require_access = os.getenv("DASHBOARD_REQUIRE_ACCESS", "true").lower() != "false"
    access_email = request.headers.get("cf-access-authenticated-user-email")
    if require_access and not access_email:
        return HTMLResponse("Cloudflare Access required.", status_code=403)
    request.state.user_email = access_email or "local"
    return await call_next(request)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def overview(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "active": "overview",
            "overview": collect_overview(),
            "calls": recent_calls(5),
        },
    )


@app.get("/live", response_class=HTMLResponse)
def live(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "live.html",
        {"active": "live", "live": live_call()},
    )


@app.get("/history", response_class=HTMLResponse)
def history(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "active": "history",
            "calls": recent_calls(50),
            "storage": recording_storage(),
        },
    )


@app.get("/history/{call_id}", response_class=HTMLResponse)
def call_detail(request: Request, call_id: str) -> HTMLResponse:
    if not valid_id(call_id):
        return HTMLResponse("Call not found", status_code=404)
    call = call_by_id(call_id)
    if not call:
        return HTMLResponse("Call not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "call_detail.html",
        {"active": "history", "call": call, "segments": audio_segments(call_id)},
    )


@app.get("/audio/{call_id}/{filename}")
def call_audio(request: Request, call_id: str, filename: str, download: bool = False) -> FileResponse:
    path = safe_audio_path(call_id, filename)
    if not path:
        return HTMLResponse("Audio not found", status_code=404)
    logger.info("audio_access call_id=%s file=%s user=%s download=%s", call_id, filename, _user(request), download)
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=filename if download else None,
        headers={"Content-Disposition": f"{'attachment' if download else 'inline'}; filename=\"{filename}\""},
    )


@app.get("/tasks", response_class=HTMLResponse)
def tasks(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {"active": "tasks", "items": task_items()},
    )


@app.get("/menu", response_class=HTMLResponse)
def phone_menu(request: Request) -> HTMLResponse:
    settings = get_settings()
    path = settings.config_dir / "phone_menu.json"
    config = load_menu_config(path)
    raw = path.read_text(encoding="utf-8") if path.exists() else menu_config_json(default=True)
    return templates.TemplateResponse(
        request,
        "menu.html",
        {
            "active": "menu",
            "menu": config,
            "config_json": raw,
            "message": "",
            "error": "",
        },
    )


@app.post("/menu", response_class=HTMLResponse)
def phone_menu_save(request: Request, config_json: str = Form(...)) -> HTMLResponse:
    settings = get_settings()
    path = settings.config_dir / "phone_menu.json"
    tmp = path.with_suffix(".json.tmp")
    error = ""
    message = ""
    try:
        validate_menu_config_json(config_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(config_json, encoding="utf-8")
        config = load_menu_config(tmp)
        path.write_text(config_json, encoding="utf-8")
        tmp.unlink(missing_ok=True)
        message = "Menue gespeichert. Neustart des AGI ist nicht noetig; neue Calls laden die Konfiguration."
        logger.info("phone_menu_saved user=%s items=%s", _user(request), len(config.items))
    except Exception as exc:
        tmp = path.with_suffix(".json.tmp")
        tmp.unlink(missing_ok=True)
        config = load_menu_config(path)
        error = f"Konfiguration ungueltig: {exc}"
        logger.exception("phone_menu_save_failed user=%s", _user(request))
    return templates.TemplateResponse(
        request,
        "menu.html",
        {
            "active": "menu",
            "menu": config,
            "config_json": config_json,
            "message": message,
            "error": error,
        },
    )


def validate_menu_config_json(config_json: str) -> None:
    parsed = json.loads(config_json)
    if not isinstance(parsed, dict):
        raise ValueError("root must be an object")
    items = parsed.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    valid_actions = {action.value for action in HybridAction}
    keys = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")
        key = str(item.get("key", ""))
        action = str(item.get("action", ""))
        if not key:
            raise ValueError(f"item {index} has no key")
        if key in keys:
            raise ValueError(f"duplicate key {key}")
        if action not in valid_actions:
            raise ValueError(f"invalid action {action}")
        keys.add(key)


@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "logs.html",
        {"active": "logs", "logs": collect_logs()},
    )


@app.get("/tts", response_class=HTMLResponse)
def tts_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tts.html",
        {
            "active": "tts",
            "config": load_tts_config(),
            "voices": available_tts_voices(),
            "sample_url": "",
            "message": "",
            "error": "",
        },
    )


@app.post("/tts", response_class=HTMLResponse)
def tts_save(
    request: Request,
    provider: str = Form("piper"),
    voice: str = Form(...),
    fallback_voice: str = Form(...),
    length_scale: float = Form(...),
    sentence_silence: float = Form(...),
    volume: float = Form(...),
    test_text: str = Form(""),
    action: str = Form("save"),
) -> HTMLResponse:
    message = ""
    error = ""
    sample_url = ""
    try:
        config = validate_tts_config(
            {
                "provider": provider,
                "voice": voice,
                "fallback_voice": fallback_voice,
                "length_scale": length_scale,
                "sentence_silence": sentence_silence,
                "volume": volume,
            }
        )
        if action == "test":
            text = test_text.strip() or "Guten Tag und herzlich willkommen bei OpenVoice AI. Wie kann ich Ihnen helfen?"
            sample_dir = get_settings().app_base_dir / "tts_voice_samples"
            sample_dir.mkdir(parents=True, exist_ok=True)
            sample_path = sample_dir / "dashboard-test.wav"
            synthesize_with_config(text, sample_path, config)
            sample_url = "/tts/sample/dashboard-test.wav"
            message = "Sprachprobe erzeugt. Bitte über Kopfhörer und Telefonpfad vergleichen."
            logger.info("tts_sample_generated user=%s voice=%s", _user(request), config.voice)
        else:
            save_tts_config(config)
            message = "TTS-Konfiguration gespeichert. Die alte Stimme bleibt als Fallback erhalten."
            logger.info("tts_config_saved user=%s voice=%s fallback=%s", _user(request), config.voice, config.fallback_voice)
    except Exception as exc:
        config = load_tts_config()
        error = f"TTS-Konfiguration konnte nicht verarbeitet werden: {exc}"
        logger.exception("tts_config_failed user=%s", _user(request))
    return templates.TemplateResponse(
        request,
        "tts.html",
        {
            "active": "tts",
            "config": config,
            "voices": available_tts_voices(),
            "sample_url": sample_url,
            "message": message,
            "error": error,
            "test_text": test_text,
        },
    )


@app.get("/tts/sample/{filename}")
def tts_sample(request: Request, filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename or not re.fullmatch(r"[A-Za-z0-9_.-]+\.wav", filename):
        return HTMLResponse("Sample not found", status_code=404)
    path = get_settings().app_base_dir / "tts_voice_samples" / filename
    if not path.exists() or path.suffix.lower() != ".wav":
        return HTMLResponse("Sample not found", status_code=404)
    logger.info("tts_sample_access user=%s file=%s", _user(request), filename)
    return FileResponse(path, media_type="audio/wav", filename=filename)


@app.get("/email", response_class=HTMLResponse)
def email_page(request: Request) -> HTMLResponse:
    drafts = list_drafts()
    grouped = {
        "internal_sent": [item for item in drafts if item.get("audience") == "internal" and item["status"] == "sent"],
        "internal_failed": [item for item in drafts if item.get("audience") == "internal" and item["status"] in {"failed", "error"}],
        "external_draft": [item for item in drafts if item.get("audience", "external") == "external" and item["status"] == "draft"],
        "external_sent": [item for item in drafts if item.get("audience", "external") == "external" and item["status"] == "sent"],
        "external_queued": [item for item in drafts if item.get("audience", "external") == "external" and item["status"] == "queued"],
        "external_failed": [item for item in drafts if item.get("audience", "external") == "external" and item["status"] in {"failed", "error"}],
    }
    return templates.TemplateResponse(
        request,
        "email.html",
        {"active": "email", "groups": grouped},
    )


@app.get("/email/drafts/{draft_id}", response_class=HTMLResponse)
def email_draft_view(request: Request, draft_id: int) -> HTMLResponse:
    draft = get_draft(draft_id)
    if not draft:
        return HTMLResponse("Draft not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "email_draft.html",
        {"active": "email", "draft": draft},
    )


@app.post("/email/drafts/{draft_id}/edit")
def email_draft_edit(
    request: Request,
    draft_id: int,
    recipient: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    internal_note: str = Form(""),
) -> RedirectResponse:
    update_draft(draft_id, recipient.strip(), subject.strip(), body, internal_note)
    logger.info("email_draft_updated draft_id=%s user=%s recipient=%s subject=%s", draft_id, _user(request), recipient, subject)
    return RedirectResponse(f"/email/drafts/{draft_id}", status_code=303)


@app.post("/email/drafts/{draft_id}/delete")
def email_draft_delete(request: Request, draft_id: int) -> RedirectResponse:
    delete_draft(draft_id)
    logger.info("email_draft_deleted draft_id=%s user=%s", draft_id, _user(request))
    return RedirectResponse("/email", status_code=303)


@app.post("/email/drafts/{draft_id}/send")
def email_draft_send(request: Request, draft_id: int) -> RedirectResponse:
    draft = get_draft(draft_id)
    if not draft:
        return RedirectResponse("/email", status_code=303)
    if draft.get("audience") == "internal":
        logger.warning("internal_email_manual_send_blocked draft_id=%s user=%s", draft_id, _user(request))
        return RedirectResponse(f"/email/drafts/{draft_id}", status_code=303)
    try:
        send_message(draft["recipient"], draft["subject"], draft["body"])
        mark_sent(draft_id)
        logger.info("email_draft_sent draft_id=%s user=%s recipient=%s subject=%s", draft_id, _user(request), draft["recipient"], draft["subject"])
    except Exception as exc:
        mark_error(draft_id, str(exc))
        logger.exception("email_draft_send_failed draft_id=%s user=%s", draft_id, _user(request))
    return RedirectResponse(f"/email/drafts/{draft_id}", status_code=303)


@app.post("/email/test-send")
def email_test_send(request: Request, recipient: str = Form(...)) -> RedirectResponse:
    settings = get_settings()
    subject = "Phone-Agent Testmail"
    body = "Dies ist eine manuell ausgeloeste Testmail aus dem Phone-Agent Dashboard."
    try:
        send_message(recipient.strip(), subject, body)
        logger.info("email_test_sent user=%s recipient=%s", _user(request), recipient)
    except Exception:
        logger.exception("email_test_failed user=%s recipient=%s", _user(request), recipient)
    return RedirectResponse("/email", status_code=303)


@app.get("/ai", response_class=HTMLResponse)
def ai(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "ai.html",
        {"active": "ai", "ai": collect_ai()},
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active": "settings",
            "settings": safe_settings(),
            "form": settings_form_data(),
            "message": "",
            "error": "",
        },
    )


@app.post("/settings", response_class=HTMLResponse)
def settings_save(
    request: Request,
    whisper_model: str = Form(...),
    record_seconds: int = Form(...),
    silence_seconds: float = Form(...),
    min_record_seconds: float = Form(...),
    post_playback_wait_seconds: float = Form(...),
    max_turns: int = Form(...),
    max_llm_rounds_per_call: int = Form(...),
    llm_provider: str = Form(...),
    nvidia_model: str = Form(...),
    openrouter_model: str = Form(...),
    openrouter_fallback_model: str = Form(...),
    openrouter_max_tokens: int = Form(...),
    openrouter_temperature: float = Form(...),
    openrouter_top_p: float = Form(...),
) -> HTMLResponse:
    message = ""
    error = ""
    try:
        overrides = validate_runtime_settings(
            {
                "whisper_model": whisper_model,
                "whisper_language": "de",
                "record_seconds": record_seconds,
                "silence_seconds": silence_seconds,
                "min_record_seconds": min_record_seconds,
                "post_playback_wait_seconds": post_playback_wait_seconds,
                "max_turns": max_turns,
                "max_llm_rounds_per_call": max_llm_rounds_per_call,
                "llm_provider": llm_provider,
                "nvidia_model": nvidia_model,
                "openrouter_model": openrouter_model,
                "openrouter_fallback_model": openrouter_fallback_model,
                "openrouter_max_tokens": openrouter_max_tokens,
                "openrouter_temperature": openrouter_temperature,
                "openrouter_top_p": openrouter_top_p,
            }
        )
        save_runtime_settings(overrides)
        get_settings.cache_clear()
        message = "Einstellungen gespeichert. Neue Calls verwenden diese Werte; laufende Gespräche bleiben unverändert."
        logger.info("runtime_settings_saved user=%s keys=%s", _user(request), ",".join(sorted(overrides)))
    except Exception as exc:
        error = f"Einstellungen konnten nicht gespeichert werden: {exc}"
        logger.exception("runtime_settings_save_failed user=%s", _user(request))
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active": "settings",
            "settings": safe_settings(),
            "form": settings_form_data(),
            "message": message,
            "error": error,
        },
    )


@app.get("/partials/live", response_class=HTMLResponse)
def live_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/live_panel.html", {"live": live_call()})


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    return {
        "overview": collect_overview(),
        "system": system_snapshot(),
        "asterisk": asterisk_snapshot(),
        "recordings": recording_storage(),
    }


@app.get("/api/live")
def api_live() -> dict[str, Any]:
    return {"live": live_call(), "asterisk": asterisk_snapshot()}


@app.get("/api/calls")
def api_calls(limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 100))
    return {"calls": recent_calls(safe_limit)}


@app.get("/api/ai")
def api_ai() -> dict[str, Any]:
    return collect_ai()


def collect_overview() -> dict[str, Any]:
    settings = get_settings()
    calls = recent_calls(20)
    system = system_snapshot()
    asterisk = asterisk_snapshot()
    return {
        "live_status": dashboard_status(asterisk),
        "sip_status": asterisk["sip_registration"],
        "agent_status": asterisk["service"],
        "asterisk_channels": asterisk["channels"],
        "cpu": system["cpu_percent"],
        "ram": system["ram_percent"],
        "disk": system["disk_percent"],
        "model": settings.whisper_model,
        "provider": settings.llm_provider,
        "last_call": calls[0] if calls else None,
        "avg_response": average_response_time(),
        "data_source": "live system, logs, transcripts, recordings",
    }


def live_call() -> dict[str, Any] | None:
    call_id = latest_call_id()
    if not call_id:
        return None
    lines = log_lines(call_id)
    finished = any("call_finished" in line for line in lines)
    start_ts = parse_log_time(lines[0]) if lines else None
    last_state = last_matching(lines, "conversation_state_")
    transcript = [extract_after(line, "text=") for line in lines if "transcript_full" in line]
    return {
        "call_id": call_id,
        "phone": extract_regex(lines[0], r"caller_id=([^ ]+)") if lines else "",
        "duration": max(0, int(time.time() - start_ts.timestamp())) if start_ts and not finished else None,
        "step": "finished" if finished else phase_from_lines(lines),
        "transcript": transcript,
        "intent": extract_regex(last_state, r"intent=([^ ]+)") if last_state else "",
        "reply": extract_regex(last_state, r"assistant_reply=(.*?) rolling_summary=") if last_state else "",
    }


def recent_calls(limit: int) -> list[dict[str, Any]]:
    settings = get_settings()
    calls = []
    for path in sorted(settings.transcripts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not is_real_call_id(path.stem):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        call_id = path.stem
        appt = data.get("appointment") or {}
        calls.append(call_row(call_id, data, appt))
        if len(calls) >= limit:
            break
    return calls


def call_by_id(call_id: str) -> dict[str, Any] | None:
    if not valid_id(call_id):
        return None
    path = get_settings().transcripts_dir / f"{call_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return call_row(call_id, data, data.get("appointment") or {})


def call_row(call_id: str, data: dict[str, Any], appt: dict[str, Any]) -> dict[str, Any]:
    segments = audio_segments(call_id)
    return {
        "call_id": call_id,
        "date": data.get("started_at", ""),
        "phone": data.get("caller_id", ""),
        "duration": call_duration(call_id),
        "audio": latest_audio(call_id),
        "audio_count": len(segments),
        "audio_segments": segments[:3],
        "transcript": " / ".join(item.get("content", "") for item in data.get("transcript", []) if item.get("role") == "user"),
        "summary": data.get("summary", ""),
        "appointment": ", ".join(str(appt.get(k) or "") for k in ("name", "date", "time", "topic", "phone")).strip(", "),
        "status": "done" if data.get("ended") else "open",
    }


def task_items() -> list[dict[str, str]]:
    rows = []
    for call in recent_calls(100):
        text = f"{call['summary']} {call['transcript']}".lower()
        if any(word in text for word in ("termin", "rueckruf", "rückruf", "nachricht")) or call["appointment"]:
            rows.append({"type": "Termin/Rueckruf/Nachricht", "phone": call["phone"], "summary": call["summary"] or call["transcript"], "status": call["status"]})
    return rows


def collect_logs() -> dict[str, str]:
    return {
        "phone_agent": "\n".join(tail(get_settings().logs_dir / "phone-agent.log", 120)),
        "asterisk": run(["asterisk", "-rx", "core show channels"]).strip(),
        "errors": "\n".join(line for line in tail(get_settings().logs_dir / "phone-agent.log", 300) if "ERROR" in line or "WARNING" in line),
        "healthcheck": run([str(get_settings().app_base_dir / "scripts" / "healthcheck.sh")]),
    }


def collect_ai() -> dict[str, Any]:
    settings = get_settings()
    usage_lines = [line for line in tail(settings.logs_dir / "phone-agent.log", 500) if "llm_usage" in line]
    return {
        "nvidia_model": settings.nvidia_model,
        "openrouter_status": "configured" if bool(settings.openrouter_api_key) else "missing",
        "provider": settings.llm_provider,
        "usage": usage_lines[-20:],
        "avg_llm": average_phase_time("llm"),
        "cost": "not available",
    }


def safe_settings() -> dict[str, str]:
    settings = get_settings()
    tts_config = load_tts_config()
    return {
        "STT": f"{settings.whisper_model}, {settings.whisper_language}, record={settings.record_seconds}s, silence={settings.silence_seconds}s",
        "TTS": f"{tts_config.provider}, voice={tts_config.voice}, fallback={tts_config.fallback_voice}",
        "SIP": sip_status(),
        "Cloudflare": cloudflared_status(),
        "Mail": f"SMTP={mask_host(settings.smtp_host)}, IMAP={mask_host(settings.imap_host)}, from={mask_email(settings.mail_from)}",
        "n8n": "configured" if settings.n8n_webhook_url else "not configured",
        "Google Calendar": "managed in n8n",
    }


def settings_form_data() -> dict[str, Any]:
    settings = get_settings()
    overrides = load_runtime_settings(settings)
    return {
        "whisper_models": ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        "llm_providers": ["nvidia", "openrouter"],
        "overrides": overrides,
        "values": {
            "whisper_model": settings.whisper_model,
            "record_seconds": settings.record_seconds,
            "silence_seconds": settings.silence_seconds,
            "min_record_seconds": settings.min_record_seconds,
            "post_playback_wait_seconds": settings.post_playback_wait_seconds,
            "max_turns": settings.max_turns,
            "max_llm_rounds_per_call": settings.max_llm_rounds_per_call,
            "llm_provider": settings.llm_provider,
            "nvidia_model": settings.nvidia_model,
            "openrouter_model": settings.openrouter_model,
            "openrouter_fallback_model": settings.openrouter_fallback_model,
            "openrouter_max_tokens": settings.openrouter_max_tokens,
            "openrouter_temperature": settings.openrouter_temperature,
            "openrouter_top_p": settings.openrouter_top_p,
        },
    }


def validate_runtime_settings(data: dict[str, Any]) -> dict[str, Any]:
    whisper_model = str(data["whisper_model"]).strip()
    if whisper_model not in {"tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"}:
        raise ValueError("Ungültiges STT-Modell")
    provider = str(data["llm_provider"]).strip()
    if provider not in {"nvidia", "openrouter"}:
        raise ValueError("Ungültiger LLM-Provider")
    values = {
        "whisper_model": whisper_model,
        "whisper_language": "de",
        "record_seconds": _bounded_int(data["record_seconds"], 3, 30, "record_seconds"),
        "silence_seconds": _bounded_float(data["silence_seconds"], 0.5, 5.0, "silence_seconds"),
        "min_record_seconds": _bounded_float(data["min_record_seconds"], 0.0, 5.0, "min_record_seconds"),
        "post_playback_wait_seconds": _bounded_float(data["post_playback_wait_seconds"], 0.0, 3.0, "post_playback_wait_seconds"),
        "max_turns": _bounded_int(data["max_turns"], 1, 20, "max_turns"),
        "max_llm_rounds_per_call": _bounded_int(data["max_llm_rounds_per_call"], 1, 10, "max_llm_rounds_per_call"),
        "llm_provider": provider,
        "nvidia_model": _safe_model_name(data["nvidia_model"], "nvidia_model"),
        "openrouter_model": _safe_model_name(data["openrouter_model"], "openrouter_model"),
        "openrouter_fallback_model": _safe_model_name(data["openrouter_fallback_model"], "openrouter_fallback_model"),
        "openrouter_max_tokens": _bounded_int(data["openrouter_max_tokens"], 1, 80, "openrouter_max_tokens"),
        "openrouter_temperature": _bounded_float(data["openrouter_temperature"], 0.0, 1.0, "openrouter_temperature"),
        "openrouter_top_p": _bounded_float(data["openrouter_top_p"], 0.1, 1.0, "openrouter_top_p"),
    }
    if values["min_record_seconds"] > values["record_seconds"]:
        raise ValueError("Mindestaufnahme darf nicht länger als RECORD_SECONDS sein")
    return values


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} muss zwischen {minimum} und {maximum} liegen")
    return number


def _bounded_float(value: Any, minimum: float, maximum: float, name: str) -> float:
    number = float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} muss zwischen {minimum} und {maximum} liegen")
    return number


def _safe_model_name(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 120:
        raise ValueError(f"{name} ist ungültig")
    if not re.fullmatch(r"[A-Za-z0-9._:/+-]+", text):
        raise ValueError(f"{name} enthält ungültige Zeichen")
    return text


def mask_email(value: str) -> str:
    if not value or "@" not in value:
        return "not configured"
    name, domain = value.split("@", 1)
    return f"{name[:2]}***@{domain}"


def mask_host(value: str) -> str:
    return value or "not configured"


def _user(request: Request) -> str:
    return getattr(request.state, "user_email", "unknown")


def system_snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(get_settings().app_base_dir))
    boot = datetime.fromtimestamp(psutil.boot_time()).isoformat(timespec="seconds")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_percent": memory.percent,
        "ram_used": human_size(memory.used),
        "ram_total": human_size(memory.total),
        "disk_percent": disk.percent,
        "disk_used": human_size(disk.used),
        "disk_total": human_size(disk.total),
        "boot_time": boot,
    }


def asterisk_snapshot() -> dict[str, Any]:
    channels_raw = run(["asterisk", "-rx", "core show channels"])
    return {
        "service": service_state("asterisk"),
        "sip_registration": sip_status(),
        "channels": parse_asterisk_channels(channels_raw),
        "channels_raw": channels_raw.strip(),
        "cloudflared": cloudflared_status(),
    }


def dashboard_status(asterisk: dict[str, Any]) -> str:
    if asterisk["channels"].get("active_calls", 0) > 0:
        return "active call"
    if asterisk["service"] in {"active", "unknown"}:
        return "online"
    return "degraded"


def sip_status() -> str:
    out = run(["asterisk", "-rx", "pjsip show registrations"])
    lowered = out.lower()
    if not out.strip() or "not found" in lowered or "no such file" in lowered or "winerror 2" in lowered:
        return "unknown"
    if "registered" in lowered:
        return "Registered"
    if "rejected" in lowered:
        return "Rejected"
    if "no objects found" in lowered or "unregistered" in lowered:
        return "Not registered"
    return "unknown"


def service_state(name: str) -> str:
    out = run(["systemctl", "is-active", name]).strip()
    lowered = out.lower()
    if not out or "not found" in lowered or "no such file" in lowered or "winerror 2" in lowered:
        return "unknown"
    return out.splitlines()[0]


def cloudflared_status() -> str:
    out = service_state("cloudflared")
    if out != "unknown":
        return out
    process_names = {proc.info.get("name", "").lower() for proc in psutil.process_iter(["name"])}
    return "running" if any("cloudflared" in name for name in process_names) else "unknown"


def parse_asterisk_channels(raw: str) -> dict[str, Any]:
    text = raw.strip()
    lowered = text.lower()
    if not text or "not found" in lowered or "no such file" in lowered or "winerror 2" in lowered:
        return {"active_channels": 0, "active_calls": 0, "summary": "unknown"}
    channels = extract_regex(text, r"(\d+)\s+active channels?")
    calls = extract_regex(text, r"(\d+)\s+active calls?")
    return {
        "active_channels": int(channels) if channels else 0,
        "active_calls": int(calls) if calls else 0,
        "summary": last_matching(text.splitlines(), "active calls") or text.splitlines()[-1],
    }


def latest_call_id() -> str | None:
    ids = []
    for line in tail(get_settings().logs_dir / "phone-agent.log", 1000):
        if "call_started call_id=" in line and "call_id=sim-" not in line:
            call_id = extract_regex(line, r"call_id=([^ ]+)")
            if is_real_call_id(call_id):
                ids.append(call_id)
    return ids[-1] if ids else None


def log_lines(call_id: str) -> list[str]:
    return [line for line in tail(get_settings().logs_dir / "phone-agent.log", 2000) if call_id in line]


def tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return data[-lines:]


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=6)
        return result.stdout or result.stderr
    except Exception as exc:
        return str(exc)


def call_duration(call_id: str) -> str:
    lines = log_lines(call_id)
    start = parse_log_time(lines[0]) if lines else None
    end_line = last_matching(lines, "call_finished") or (lines[-1] if lines else "")
    end = parse_log_time(end_line) if end_line else None
    if start and end:
        return f"{int((end - start).total_seconds())}s"
    return ""


def latest_audio(call_id: str) -> str:
    paths = sorted(recording_paths(call_id), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(paths[0]) if paths else ""


def recording_paths(call_id: str) -> list[Path]:
    if not valid_id(call_id):
        return []
    settings = get_settings()
    paths = list((settings.recordings_dir / call_id).glob(f"{call_id}-*.wav"))
    paths.extend(settings.recordings_dir.glob(f"{call_id}-*.wav"))
    return sorted({path.resolve() for path in paths if "-reply" not in path.name and ".stt" not in path.name})


def audio_segments(call_id: str) -> list[dict[str, Any]]:
    segments = []
    for path in recording_paths(call_id):
        segments.append(
            {
                "name": path.name,
                "size": human_size(path.stat().st_size),
                "duration": wav_duration(path),
                "url": f"/audio/{call_id}/{path.name}",
                "download_url": f"/audio/{call_id}/{path.name}?download=true",
            }
        )
    return segments


def safe_audio_path(call_id: str, filename: str) -> Path | None:
    if not valid_id(call_id) or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
        return None
    for path in recording_paths(call_id):
        if path.name == filename and path.exists():
            return path
    return None


def wav_duration(path: Path) -> str:
    try:
        import wave

        with wave.open(str(path), "rb") as wav:
            return f"{wav.getnframes() / float(wav.getframerate()):.2f}s"
    except Exception:
        return "n/a"


def recording_storage() -> dict[str, str]:
    root = get_settings().recordings_dir
    total = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    return {"used": human_size(total), "retention": "keine automatische Loeschung"}


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024


def menu_config_json(default: bool = False) -> str:
    config = default_menu_config() if default else load_menu_config()
    return json.dumps(
        {
            "prompt": config.prompt,
            "timeout_prompt": config.timeout_prompt,
            "invalid_prompt": config.invalid_prompt,
            "max_retries": config.max_retries,
            "items": [
                {
                    "key": item.key,
                    "action": item.action.value,
                    "label": item.label,
                    "speech": list(item.speech),
                    "enabled": item.enabled,
                }
                for item in config.items
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def valid_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value))


def is_real_call_id(call_id: str) -> bool:
    if not valid_id(call_id):
        return False
    lowered = call_id.lower()
    return not lowered.startswith(("sim-", "test-", "demo-", "sample-"))


def average_response_time() -> str:
    vals = []
    for phase in ("record", "stt", "llm", "tts"):
        value = average_phase_time(phase)
        if value is not None:
            vals.append(value)
    return f"{sum(vals):.1f}s" if vals else "n/a"


def average_phase_time(phase: str) -> float | None:
    values = []
    pattern = re.compile(rf"phase={re.escape(phase)} seconds=([0-9.]+)")
    for line in tail(get_settings().logs_dir / "phone-agent.log", 800):
        match = pattern.search(line)
        if match:
            values.append(float(match.group(1)))
    return round(sum(values[-20:]) / len(values[-20:]), 3) if values else None


def phase_from_lines(lines: list[str]) -> str:
    for phase in ("record", "stt", "llm", "tts", "playback"):
        if last_matching(lines, f"phase={phase}"):
            current = phase
    return locals().get("current", "starting")


def parse_log_time(line: str) -> datetime | None:
    try:
        return datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None


def last_matching(lines: list[str], needle: str) -> str:
    for line in reversed(lines):
        if needle in line:
            return line
    return ""


def extract_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def extract_after(text: str, marker: str) -> str:
    return text.split(marker, 1)[1].strip() if marker in text else ""
