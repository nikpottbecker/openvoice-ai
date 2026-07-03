import asyncio
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from .calendar import send_calendar_action
from .config import get_settings
from .llm import get_agent_reply
from .models import AgentState, LLMResult

logger = logging.getLogger(__name__)


class PhoneAgent:
    def __init__(self, call_id: str, caller_id: str):
        self.settings = get_settings()
        self.state = AgentState(call_id=call_id, caller_id=caller_id)

    def greeting(self) -> str:
        return "Hallo, hier ist der digitale Assistent. Worum geht es?"

    async def handle_turn(self, user_text: str) -> LLMResult:
        user_text = " ".join(user_text.strip().split())
        self.state.transcript.append({"role": "user", "content": user_text})
        self.state.llm_rounds += 1
        self._apply_hard_intent_detection(user_text)
        direct_result = self._handle_direct_appointment_start(user_text)
        if direct_result:
            self.state.transcript.append({"role": "assistant", "content": direct_result.reply})
            self.state.summary = (direct_result.summary or self.state.summary)[:600]
            self.state.intent = direct_result.intent
            self.state.appointment = direct_result.appointment
            self._persist_state()
            logger.info(
                "conversation_state_direct call_id=%s user_text=%s intent=%s missing_fields=%s assistant_reply=%s rolling_summary=%s",
                self.state.call_id,
                user_text,
                self.state.intent,
                ",".join(self.state.appointment.missing_fields()),
                direct_result.reply,
                self.state.summary,
            )
            return direct_result

        slot_result = self._handle_expected_slot(user_text)
        if slot_result:
            self.state.transcript.append({"role": "assistant", "content": slot_result.reply})
            self.state.summary = (slot_result.summary or self.state.summary)[:600]
            self.state.intent = slot_result.intent
            self.state.appointment = slot_result.appointment
            self._persist_state()
            logger.info(
                "conversation_state_slot call_id=%s user_text=%s intent=%s missing_fields=%s assistant_reply=%s rolling_summary=%s",
                self.state.call_id,
                user_text,
                self.state.intent,
                ",".join(self.state.appointment.missing_fields()),
                slot_result.reply,
                self.state.summary,
            )
            return slot_result

        logger.info(
            "conversation_state_pre_llm call_id=%s user_text=%s rolling_summary=%s intent=%s missing_fields=%s",
            self.state.call_id,
            user_text,
            self.state.summary,
            self.state.intent,
            ",".join(self.state.appointment.missing_fields()),
        )
        result = await get_agent_reply(self.state, user_text)
        result = self._force_appointment_flow(result, user_text)
        self.state.transcript.append({"role": "assistant", "content": result.reply})
        self.state.intent = result.intent
        self.state.appointment = result.appointment
        self.state.summary = (result.summary or self.state.summary)[:600]
        self.state.ended = result.should_end_call
        logger.info(
            "conversation_state_post_llm call_id=%s intent=%s missing_fields=%s assistant_reply=%s rolling_summary=%s",
            self.state.call_id,
            self.state.intent,
            ",".join(self.state.appointment.missing_fields()),
            result.reply,
            self.state.summary,
        )

        if result.action and result.intent == "appointment":
            sent = await send_calendar_action(self._calendar_payload(result))
            logger.info("calendar_action_sent=%s call_id=%s", sent, self.state.call_id)

        self._persist_state()
        return result

    def _calendar_payload(self, result: LLMResult) -> dict:
        appointment = result.appointment
        payload = {
            "type": "appointment",
            "caller_id": self.state.caller_id,
            "call_id": self.state.call_id,
            "name": appointment.name,
            "date": appointment.date,
            "time": appointment.time,
            "topic": appointment.topic,
            "phone": appointment.phone,
            "summary": result.summary or self.state.summary,
            "transcript_path": str(self._state_path()),
        }
        payload.update(result.action or {})
        return payload

    def _state_path(self) -> Path:
        return self.settings.transcripts_dir / f"{self.state.call_id}.json"

    def _persist_state(self) -> None:
        self._state_path().write_text(
            json.dumps(self.state.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _apply_hard_intent_detection(self, user_text: str) -> None:
        text = user_text.lower()
        signals = self._appointment_signal_count(text)
        if re.search(r"\b(termin|vereinbaren|morgen|heute|uhr|fotoshooting|foto.?shooting|rueckruf|ruckruf)\b", text) or signals:
            self.state.intent = "callback" if "rueckruf" in text or "ruckruf" in text else "appointment"
            if not self.state.summary:
                self.state.summary = user_text[:300]

    def _appointment_signal_count(self, text: str) -> int:
        keywords = ("termin", "machen", "morgen", "uhr", "fotoshooting", "shooting", "vereinbaren")
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        count = 0
        for keyword in keywords:
            if keyword in text:
                count += 1
                continue
            if any(SequenceMatcher(None, token, keyword).ratio() >= 0.74 for token in tokens):
                count += 1
        return count

    def _force_appointment_flow(self, result: LLMResult, user_text: str) -> LLMResult:
        text = " ".join([user_text, result.reply, self.state.summary]).lower()
        appointment_detected = self.state.intent == "appointment" or any(
            word in text for word in ("termin", "vereinbaren", "morgen", "heute", "uhr", "fotoshooting", "shooting")
        )
        if not appointment_detected:
            return result

        result.intent = "appointment"
        appointment = result.appointment
        if self.state.appointment.name and not appointment.name:
            appointment.name = self.state.appointment.name
        if self.state.appointment.date and not appointment.date:
            appointment.date = self.state.appointment.date
        if self.state.appointment.time and not appointment.time:
            appointment.time = self.state.appointment.time
        if self.state.appointment.topic and not appointment.topic:
            appointment.topic = self.state.appointment.topic
        if self.state.appointment.phone and not appointment.phone:
            appointment.phone = self.state.appointment.phone
        result.appointment = appointment

        generic = "wie kann ich" in result.reply.lower() or result.reply.lower().strip() in {"hallo!", "hallo."}
        if generic or not appointment.name:
            result.reply = "Gerne. Wie ist Ihr Name?"
            self.state.expected_slot = "name"
        elif not appointment.date or not appointment.time:
            result.reply = "Danke. An welchem Tag und um welche Uhrzeit soll der Termin sein?"
            self.state.expected_slot = "date_time"
        elif not appointment.topic:
            result.reply = "Worum geht es bei dem Termin?"
            self.state.expected_slot = "topic"
        elif not appointment.phone:
            result.reply = "Unter welcher Telefonnummer koennen wir Sie erreichen?"
            self.state.expected_slot = "phone"
        elif not appointment.confirmed:
            result.reply = "Danke. Ich leite die Anfrage weiter. Passt das so?"
            self.state.expected_slot = "confirmed"
        return result

    def _handle_direct_appointment_start(self, user_text: str) -> LLMResult | None:
        if self.state.intent != "appointment" or self.state.expected_slot:
            return None
        if self._appointment_signal_count(user_text.lower()) < 2:
            self.state.expected_slot = "appointment_confirm"
            return self._slot_reply("Ich habe verstanden, dass es um einen Termin gehen koennte. Stimmt das?")
        self._prefill_appointment_from_text(user_text)
        if not self.state.appointment.name:
            self.state.expected_slot = "name"
            return self._slot_reply("Gerne. Wie ist Ihr Name?")
        return None

    def _handle_expected_slot(self, user_text: str) -> LLMResult | None:
        slot = self.state.expected_slot
        if not slot or self.state.intent != "appointment":
            return None

        cleaned = self._clean_slot_text(user_text)
        self.state.slot_failures[slot] = self.state.slot_failures.get(slot, 0)

        if slot == "name":
            if cleaned:
                self.state.caller_name = cleaned
                self.state.appointment.name = cleaned
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Wie ist Ihr Name?", lambda: setattr(self.state.appointment, "name", user_text or "unbekannter Name"))

        if slot == "appointment_confirm":
            text = user_text.lower()
            if any(word in text for word in ("ja", "stimmt", "genau", "termin", "passt", "richtig")):
                self.state.expected_slot = "name"
                return self._slot_reply("Gerne. Wie ist Ihr Name?")
            self.state.expected_slot = None
            self.state.intent = "unknown"
            return self._slot_reply("Okay. Worum geht es?")

        if slot == "date_time":
            if cleaned:
                self._store_date_time(cleaned)
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "An welchem Tag und um welche Uhrzeit soll der Termin sein?", lambda: self._store_date_time(user_text or "Terminzeit unklar"))

        if slot == "topic":
            if cleaned:
                self.state.appointment.topic = cleaned
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Worum geht es bei dem Termin?", lambda: setattr(self.state.appointment, "topic", user_text or "Thema unklar"))

        if slot == "phone":
            phone = self._clean_phone_text(user_text) or cleaned
            if phone:
                self.state.appointment.phone = phone
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Unter welcher Telefonnummer koennen wir Sie erreichen?", lambda: setattr(self.state.appointment, "phone", user_text or "Telefonnummer unklar"))

        if slot == "confirmed":
            text = user_text.lower()
            if any(word in text for word in ("ja", "passt", "genau", "richtig", "okay", "ok")):
                self.state.appointment.confirmed = True
                self.state.expected_slot = None
                return self._slot_reply("Danke. Ich leite die Anfrage weiter.")
            self.state.slot_failures[slot] += 1
            if self.state.slot_failures[slot] >= 2:
                self.state.expected_slot = None
                return self._slot_reply("Danke. Ich nehme die Nachricht auf und leite sie weiter.")
            return self._slot_reply("Passt das so?")

        return None

    def _retry_or_note(self, slot: str, retry_reply: str, store_note) -> LLMResult:
        self.state.slot_failures[slot] += 1
        if self.state.slot_failures[slot] >= 2:
            store_note()
            return self._slot_reply(self._next_appointment_question())
        return self._slot_reply(retry_reply)

    def _slot_reply(self, reply: str) -> LLMResult:
        return LLMResult(
            reply=reply,
            intent="appointment",
            appointment=self.state.appointment,
            summary=self._appointment_summary(),
        )

    def _clean_slot_text(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^(ich bin|mein name ist|hier ist|das ist|aehm|ae|hm)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        return cleaned

    def _clean_phone_text(self, text: str) -> str:
        cleaned = re.sub(r"[^\d+]", "", text)
        return cleaned if len(cleaned) >= 3 else ""

    def _store_date_time(self, text: str) -> None:
        lower = text.lower()
        date_match = re.search(r"\b(heute|morgen|uebermorgen|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)\b", lower)
        time_match = re.search(r"\b(\d{1,2})(?::|\.| )?(\d{2})?\s*(?:uhr)?\b", lower)
        self.state.appointment.date = date_match.group(1) if date_match else text
        if time_match:
            minute = time_match.group(2) or "00"
            self.state.appointment.time = f"{time_match.group(1)}:{minute}"
        else:
            self.state.appointment.time = text

    def _prefill_appointment_from_text(self, text: str) -> None:
        lower = text.lower()
        if not self.state.appointment.date or not self.state.appointment.time:
            self._store_date_time(text)
        if not self.state.appointment.topic:
            if "fotoshooting" in lower or "foto" in lower or "shooting" in lower:
                self.state.appointment.topic = "Fotoshooting"
            elif "video" in lower:
                self.state.appointment.topic = "Video"
            elif "livestream" in lower or "stream" in lower:
                self.state.appointment.topic = "Livestream"

    def _next_appointment_question(self) -> str:
        if not self.state.appointment.date or not self.state.appointment.time:
            self.state.expected_slot = "date_time"
            return "Danke. An welchem Tag und um welche Uhrzeit soll der Termin sein?"
        if not self.state.appointment.topic:
            self.state.expected_slot = "topic"
            return "Danke. Worum geht es bei dem Termin?"
        if not self.state.appointment.phone:
            self.state.expected_slot = "phone"
            return "Danke. Unter welcher Telefonnummer koennen wir Sie erreichen?"
        if not self.state.appointment.confirmed:
            self.state.expected_slot = "confirmed"
            return "Danke. Ich leite die Anfrage weiter. Passt das so?"
        self.state.expected_slot = None
        return "Danke. Ich leite die Anfrage weiter."

    def _appointment_summary(self) -> str:
        appt = self.state.appointment
        return (
            f"Termin: Name={appt.name or 'offen'}, Datum={appt.date or 'offen'}, "
            f"Uhrzeit={appt.time or 'offen'}, Thema={appt.topic or 'offen'}, "
            f"Telefon={appt.phone or 'offen'}."
        )


def handle_turn_sync(agent: PhoneAgent, text: str) -> LLMResult:
    return asyncio.run(agent.handle_turn(text))
