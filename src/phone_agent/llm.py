import json
import logging
from pathlib import Path
from typing import Any
from json import JSONDecodeError

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import get_settings
from .models import AgentState, LLMResult

logger = logging.getLogger(__name__)


def _infer_intent(result: LLMResult, user_text: str) -> LLMResult:
    text = _normalize_german(" ".join([user_text, result.reply, result.summary]))
    if result.intent == "unknown" and any(word in text for word in ("termin", "vereinbaren", "kalender", "uhr")):
        result.intent = "appointment"
    if result.intent == "unknown" and any(word in text for word in ("rueckruf", "zurueckrufen")):
        result.intent = "callback"
    if result.intent == "unknown" and any(word in text for word in ("spam", "werbung", "angebot")):
        result.intent = "spam"
    if result.intent == "appointment":
        generic = _normalize_german(result.reply).strip() in {
            "hallo!",
            "hallo.",
            "hallo, ich bin niks telefonassistent.",
            "wie kann ich ihnen helfen?",
        }
        if generic or not result.appointment.name:
            result.reply = "Gerne. Wie ist Ihr Name?"
    return result


def _normalize_german(text: str) -> str:
    if "\u00c3" in text or "\u00c2" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    return (
        text.lower()
        .replace("\u00e4", "ae")
        .replace("\u00f6", "oe")
        .replace("\u00fc", "ue")
        .replace("\u00df", "ss")
    )


def _parse_llm_result(content: str, state: AgentState) -> LLMResult:
    if not content:
        logger.warning("Model returned empty content")
        return LLMResult(reply="Ich habe Sie verstanden. Wie ist Ihr Name?", summary=state.summary)
    content = _extract_json_object(content)
    if content.lstrip().startswith("{") and '"reply"' in content:
        try:
            reply_fragment = content.split('"reply"', 1)[1].split(":", 1)[1].strip()
            quote = reply_fragment[0]
            if quote in ("\"", "'"):
                reply = reply_fragment[1:].split(quote, 1)[0]
                if reply:
                    return LLMResult(reply=_clean_reply(reply), summary=state.summary)
        except Exception:
            pass
    try:
        data: Any = json.loads(content)
        if "reply" not in data and any(key in data for key in ("name", "datum", "date", "uhrzeit", "time", "thema", "topic")):
            name = data.get("name") or "Ihren Namen"
            date = data.get("date") or data.get("datum") or "den genannten Tag"
            time = data.get("time") or data.get("uhrzeit") or "die genannte Uhrzeit"
            topic = data.get("topic") or data.get("thema") or "das genannte Thema"
            data = {
                "reply": f"Soll ich den Termin fuer {name} am {date} um {time} wegen {topic} eintragen?",
                "intent": "appointment",
                "appointment": {
                    "name": data.get("name"),
                    "date": data.get("date") or data.get("datum"),
                    "time": data.get("time") or data.get("uhrzeit"),
                    "topic": data.get("topic") or data.get("thema"),
                    "confirmed": False,
                },
                "summary": f"Terminwunsch: {name}, {date}, {time}, {topic}.",
                "should_end_call": False,
                "action": None,
            }
        if data.get("appointment") is None:
            data["appointment"] = {}
        if "reply" not in data:
            logger.warning("Model JSON without reply: keys=%s", ",".join(sorted(str(k) for k in data.keys())))
            return LLMResult(reply="Ich habe Sie verstanden. Wie ist Ihr Name?", summary=state.summary)
        if data.get("action") is not None and not isinstance(data.get("action"), dict):
            data["action"] = {"type": str(data["action"])}
        intent = str(data.get("intent", "unknown")).lower()
        data["intent"] = {
            "termin": "appointment",
            "termin_vereinbaren": "appointment",
            "appointment_request": "appointment",
            "rueckruf": "callback",
            "rückruf": "callback",
            "nachricht": "message",
            "werbung": "spam",
        }.get(intent, intent if intent in {"appointment", "callback", "message", "spam", "unknown"} else "unknown")
        return LLMResult.model_validate(data)
    except JSONDecodeError:
        logger.warning("Model returned plain text instead of JSON")
        cleaned = _clean_reply(content)
        return LLMResult(reply=cleaned, summary=state.summary)
    except Exception:
        logger.exception("Model returned invalid JSON: %s", content)
        return LLMResult(reply=_clean_reply(content), summary=state.summary)


def _clean_reply(content: str) -> str:
    text = " ".join(content.strip().split())
    lower = text.lower()
    if "we need" in lower or "output json" in lower or len(text) > 260:
        return "Ich habe Sie verstanden. Um welchen Namen soll es gehen?"
    parts = []
    for sep in [". ", "? ", "! "]:
        if sep in text:
            first, rest = text.split(sep, 1)
            parts.append(first + sep.strip())
            break
    return (parts[0] if parts else text[:180]).strip()


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start and '"reply"' in text[start:end + 1]:
        return text[start:end + 1]
    return content


def _system_prompt() -> str:
    settings = get_settings()
    prompt_path = settings.config_dir / "agent.system.prompt"
    if prompt_path.exists():
        base_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        fallback = Path(__file__).resolve().parents[2] / "config" / "agent.system.prompt"
        base_prompt = fallback.read_text(encoding="utf-8")

    profile_path = settings.config_dir / "agent_profile.md"
    if not profile_path.exists():
        profile_path = Path(__file__).resolve().parents[2] / "config" / "agent_profile.md"
    if profile_path.exists():
        return base_prompt + "\n\n" + profile_path.read_text(encoding="utf-8")
    return base_prompt


def _messages(state: AgentState, user_text: str) -> list[dict[str, str]]:
    state_blob = state.model_dump_json(include={"intent", "appointment", "summary"})
    return [
        {
            "role": "system",
            "content": (
                _system_prompt()
                + "\n\n"
                "Du bist ein deutscher Telefonassistent. Antworte sehr kurz. "
                "Maximal zwei Saetze, nur eine Frage. "
                "Bei Terminwunsch sammle: Name, Datum, Uhrzeit, Thema, Telefonnummer, Bestaetigung. "
                "Wenn Terminangaben fehlen, frage nach genau der naechsten fehlenden Angabe. "
                "Sage nie 'Wie kann ich Ihnen helfen?', wenn intent nicht unknown ist. "
                "Wenn Status intent appointment ist, frage nur nach dem naechsten fehlenden Feld. "
                "Antworte ausschliesslich als minifiziertes JSON mit den Feldern reply,intent,appointment,summary,should_end_call,action. "
                "Nutze exakt das Feld reply fuer den gesprochenen Satz. "
                f"Status:{state_blob}"
            ),
        },
        {"role": "user", "content": user_text},
    ]


def _estimate_tokens(messages: list[dict[str, str]], output_text: str = "") -> tuple[int, int]:
    input_chars = sum(len(m.get("content", "")) for m in messages)
    return max(1, input_chars // 4), max(1, len(output_text or "") // 4)


def _should_retry_openrouter(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
        return False
    return True


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    retry=retry_if_exception(_should_retry_openrouter),
)
async def _chat_completion(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    state: AgentState,
    user_text: str,
) -> LLMResult:
    settings = get_settings()
    if not api_key:
        raise RuntimeError(f"{provider} API key is missing")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = settings.openrouter_http_referer
        headers["X-Title"] = settings.openrouter_app_title

    messages = _messages(state, user_text)
    use_stream = settings.openrouter_stream and provider == "openrouter"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": settings.openrouter_temperature,
        "top_p": settings.openrouter_top_p,
        "max_tokens": settings.openrouter_max_tokens,
        "stream": use_stream,
    }
    if provider == "openrouter":
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=45) as client:
        if use_stream:
            content_parts: list[str] = []
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0].get("delta", {})
                        content_parts.append(delta.get("content") or "")
                    except Exception:
                        logger.debug("Ignoring malformed stream chunk: %s", chunk[:120])
            content = "".join(content_parts)
        else:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

    input_tokens, output_tokens = _estimate_tokens(messages, content or "")
    logger.info(
        "llm_usage provider=%s model=%s estimated_input_tokens=%s estimated_output_tokens=%s",
        provider,
        model,
        input_tokens,
        output_tokens,
    )
    return _parse_llm_result(content, state)


async def _openrouter_chat(model: str, state: AgentState, user_text: str) -> LLMResult:
    settings = get_settings()
    return await _chat_completion(
        "openrouter",
        "https://openrouter.ai/api/v1",
        settings.openrouter_api_key,
        model,
        state,
        user_text,
    )


async def _nvidia_chat(model: str, state: AgentState, user_text: str) -> LLMResult:
    settings = get_settings()
    return await _chat_completion(
        "nvidia",
        settings.nvidia_base_url,
        settings.nvidia_api_key,
        model,
        state,
        user_text,
    )

async def get_agent_reply(state: AgentState, user_text: str) -> LLMResult:
    settings = get_settings()
    if state.llm_rounds > settings.max_llm_rounds_per_call:
        logger.warning("llm_round_limit call_id=%s rounds=%s", state.call_id, state.llm_rounds)
        return LLMResult(
            reply="Ich habe das notiert. Bitte rufen Sie spaeter erneut an.",
            intent=state.intent,
            summary=state.summary,
            should_end_call=True,
        )
    providers: list[tuple[str, str]] = []
    if settings.llm_provider == "nvidia":
        providers.append(("nvidia", settings.nvidia_model))
    else:
        providers.append(("openrouter", settings.openrouter_model))
    providers.append(("openrouter", settings.openrouter_fallback_model))
    last_error: Exception | None = None
    for provider, model in providers:
        try:
            raw = await (_nvidia_chat(model, state, user_text) if provider == "nvidia" else _openrouter_chat(model, state, user_text))
            return _infer_intent(raw, user_text)
        except Exception as exc:
            last_error = exc
            logger.warning("LLM provider failed: provider=%s model=%s error=%s", provider, model, exc)
    logger.error("All LLM providers failed: %s", last_error)
    return LLMResult(
        reply="Entschuldigung, die KI-Verbindung ist gerade nicht erreichbar. Bitte versuchen Sie es gleich noch einmal.",
        intent="unknown",
        summary=f"KI-Verbindung fehlgeschlagen: {last_error}",
        should_end_call=True,
    )
