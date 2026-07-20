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
        return "Hallo, Nik Pottbeckers Assistent. Worum geht es?"

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
        if self.state.expected_slot and self.state.intent == "appointment":
            return
        text = self._normalize_german(user_text)
        signals = self._appointment_signal_count(text)
        if re.search(r"\b(termin|vereinbaren|morgen|heute|uhr|fotoshooting|foto.?shooting|rueckruf|ruckruf|zurueckrufen)\b", text) or signals:
            self.state.intent = "callback" if any(word in text for word in ("rueckruf", "ruckruf", "zurueckrufen")) else "appointment"
            if not self.state.summary:
                self.state.summary = user_text[:300]

    def _appointment_signal_count(self, text: str) -> int:
        text = self._normalize_german(text)
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
        text = self._normalize_german(" ".join([user_text, result.reply, self.state.summary]))
        appointment_detected = (
            self.state.intent == "appointment"
            or self._appointment_signal_count(text) >= 1
            or any(
                word in text
                for word in ("termin", "vereinbaren", "morgen", "heute", "uhr", "fotoshooting", "shooting")
            )
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
            result.reply = "Wann soll der Termin sein?"
            self.state.expected_slot = "date_time"
        elif not appointment.topic:
            result.reply = "Worum geht es?"
            self.state.expected_slot = "topic"
        elif not appointment.phone:
            result.reply = "Welche Telefonnummer?"
            self.state.expected_slot = "phone"
        elif not appointment.confirmed:
            result.reply = "Passt das so?"
            self.state.expected_slot = "confirmed"
        return result

    def _handle_direct_appointment_start(self, user_text: str) -> LLMResult | None:
        if self.state.intent != "appointment" or self.state.expected_slot:
            return None
        lower = self._normalize_german(user_text)
        explicit_appointment = any(word in lower for word in ("termin", "vereinbaren", "buchen"))
        if not explicit_appointment and self._appointment_signal_count(lower) < 2:
            self.state.expected_slot = "appointment_confirm"
            return self._slot_reply("Geht es um einen Termin?")
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

        if self._is_cancel_text(user_text):
            self.state.expected_slot = None
            self.state.intent = "unknown"
            return LLMResult(
                reply="Alles klar. Worum geht es?",
                intent="unknown",
                appointment=self.state.appointment,
                summary=self.state.summary,
            )

        if slot == "name":
            cleaned = self._correction_text(cleaned)
            cleaned = self._extract_name_and_prefill_details(cleaned)
            if cleaned:
                self.state.caller_name = cleaned
                self.state.appointment.name = cleaned
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Wie ist Ihr Name?", lambda: setattr(self.state.appointment, "name", user_text or "unbekannter Name"))

        if slot == "appointment_confirm":
            text = self._normalize_german(user_text)
            if self._is_affirmative(text) or "termin" in text:
                self.state.expected_slot = "name"
                return self._slot_reply("Gerne. Wie ist Ihr Name?")
            self.state.expected_slot = None
            self.state.intent = "unknown"
            return LLMResult(
                reply="Okay. Worum geht es?",
                intent="unknown",
                appointment=self.state.appointment,
                summary=self.state.summary,
            )

        if slot == "date_time":
            if cleaned:
                cleaned = self._correction_text(cleaned)
                if self._store_date_time(cleaned):
                    self._prefill_appointment_from_text(cleaned)
                    return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Wann soll der Termin sein?", lambda: self._store_date_time(user_text or "Terminzeit unklar", force=True))

        if slot == "topic":
            if cleaned:
                topic_text = self._correction_text(cleaned)
                phone = self._clean_phone_text(topic_text)
                if phone:
                    self.state.appointment.phone = phone
                    topic_text = self._strip_phone_from_text(topic_text)
                self.state.appointment.topic = topic_text
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Worum geht es?", lambda: setattr(self.state.appointment, "topic", user_text or "Thema unklar"))

        if slot == "phone":
            phone = self._clean_phone_text(self._correction_text(user_text))
            if phone:
                self.state.appointment.phone = phone
                return self._slot_reply(self._next_appointment_question())
            return self._retry_or_note(slot, "Welche Telefonnummer?", lambda: setattr(self.state.appointment, "phone", user_text or "Telefonnummer unklar"))

        if slot == "confirmed":
            text = self._normalize_german(user_text)
            if self._is_affirmative(text):
                self.state.appointment.confirmed = True
                self.state.expected_slot = None
                return self._slot_reply("Danke. Ich leite weiter.")
            if self._is_negative(text):
                self.state.expected_slot = None
                return self._slot_reply("Okay. Ich nehme es als Notiz auf und leite es an Nik weiter.")
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
        cleaned = re.sub(
            r"^(ich bin der|ich bin die|ich bin|ich heisse|ich heiße|mein name ist|mein vorname ist|"
            r"der name ist|hier ist|das ist|aehm|ähm|ae|hm)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        if self._is_filler_text(cleaned):
            return ""
        return cleaned

    def _clean_phone_text(self, text: str) -> str:
        text = self._replace_spoken_digits(self._normalize_german(text))
        text = re.sub(r"\bplus\s+", "+", text)
        cleaned = re.sub(r"[^\d+]", "", text)
        digit_count = len(re.sub(r"\D", "", cleaned))
        return cleaned if digit_count >= 5 else ""

    def _strip_phone_from_text(self, text: str) -> str:
        normalized = self._normalize_german(text)
        phone_start = re.search(r"\b(?:\+?\d|plus|null|eins|ein|zwei|zwo|drei|vier|fuenf|sechs|sieben|acht|neun|zehn|elf|zwoelf)", normalized)
        if not phone_start:
            return text
        cleaned = normalized[: phone_start.start()].strip(" ,.;:-")
        return cleaned or text

    def _store_date_time(self, text: str, force: bool = False) -> bool:
        lower = self._normalize_german(text)
        spoken_date = self._spoken_date(lower)
        date_match = re.search(
            r"\b(heute|morgen|uebermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|"
            r"naechste(?:n|r|s)?\s+woche(?:\s+\w+)?|"
            r"(?:naechste(?:n|r|s)?|kommende(?:n|r|s)?|diese(?:n|r|s)?)\s+"
            r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)|"
            r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)|"
            r"\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)\b",
            lower,
        )
        time_match = self._numeric_time_match(lower)
        spoken_time = self._spoken_time(lower)
        stored = False
        if date_match:
            self.state.appointment.date = date_match.group(1)
            stored = True
        elif spoken_date:
            self.state.appointment.date = spoken_date
            stored = True
        if time_match:
            minute = time_match.group(2) if time_match.lastindex and time_match.lastindex >= 2 else None
            minute = minute or "00"
            self.state.appointment.time = f"{time_match.group(1)}:{minute}"
            stored = True
        elif spoken_time:
            self.state.appointment.time = spoken_time
            stored = True
        elif "frueh" in lower or "früh" in lower or "morgens" in lower:
            self.state.appointment.time = "morgens"
            stored = True
        elif "vormittag" in lower or "vormittags" in lower:
            self.state.appointment.time = "vormittags"
            stored = True
        elif "nachmittag" in lower or "nachmittags" in lower:
            self.state.appointment.time = "nachmittags"
            stored = True
        elif "abend" in lower or "abends" in lower:
            self.state.appointment.time = "abends"
            stored = True
        elif force and not self.state.appointment.date:
            self.state.appointment.date = text
            stored = True
        elif force and not self.state.appointment.time:
            self.state.appointment.time = text
            stored = True
        return stored

    def _correction_text(self, text: str) -> str:
        normalized = self._normalize_german(text)
        match = re.search(r"\bnicht\s+.+?\s+sondern\s+(.+)$", normalized)
        if match:
            return match.group(1).strip()
        match = re.search(r"\bnicht\s+.+?,\s*(.+)$", normalized)
        if match:
            return match.group(1).strip()
        return text

    def _extract_name_and_prefill_details(self, text: str) -> str:
        normalized = self._normalize_german(text)
        signal = re.search(
            r"\b(heute|morgen|uebermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|"
            r"um|uhr|halb|viertel|dreiviertel|\d{1,2}\.\d{1,2}|fotoshooting|shooting|foto|video|livestream|stream)\b",
            normalized,
        )
        if not signal:
            return text

        prefix = normalized[: signal.start()].strip(" ,.;:-")
        if not prefix or self._is_filler_text(prefix):
            return ""

        self._prefill_appointment_from_text(normalized[signal.start() :])
        return prefix

    def _numeric_time_match(self, text: str) -> re.Match[str] | None:
        patterns = (
            r"\b(?:um|gegen)\s*(\d{1,2})\s*uhr\s*(\d{1,2})?\b",
            r"\b(?:um|gegen)\s*(\d{1,2})(?::|\.)(\d{2})\b",
            r"\b(?:um|gegen)\s*(\d{1,2})\b",
            r"\b(\d{1,2})\s*uhr\s*(\d{1,2})?\b",
            r"\b(\d{1,2}):(\d{2})\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match
        return None

    def _spoken_time(self, text: str) -> str:
        text = self._normalize_german(text)
        words = {
            "eins": 1,
            "ein": 1,
            "zwei": 2,
            "zwo": 2,
            "drei": 3,
            "vier": 4,
            "fuenf": 5,
            "fuenfzehn": 15,
            "sechs": 6,
            "sieben": 7,
            "acht": 8,
            "neun": 9,
            "zehn": 10,
            "elf": 11,
            "zwoelf": 12,
        }
        hour_token = r"([a-z]+|\d{1,2})"
        half_match = re.search(rf"\b(?:um|gegen)?\s*halb\s+{hour_token}\b", text)
        if half_match and (hour_value := self._hour_value(half_match.group(1), words)):
            hour = hour_value - 1
            if hour <= 0:
                hour = 12
            return f"{hour}:30"
        quarter_after = re.search(rf"\b(?:um|gegen)?\s*viertel\s+nach\s+{hour_token}\b", text)
        if quarter_after and (hour_value := self._hour_value(quarter_after.group(1), words)):
            return f"{hour_value}:15"
        quarter_before = re.search(rf"\b(?:um|gegen)?\s*viertel\s+vor\s+{hour_token}\b", text)
        if quarter_before and (hour_value := self._hour_value(quarter_before.group(1), words)):
            hour = hour_value - 1
            if hour <= 0:
                hour = 12
            return f"{hour}:45"
        quarter_plain = re.search(rf"\b(?:um|gegen)?\s*viertel\s+{hour_token}\b", text)
        if quarter_plain and (hour_value := self._hour_value(quarter_plain.group(1), words)):
            hour = hour_value - 1
            if hour <= 0:
                hour = 12
            return f"{hour}:15"
        three_quarter = re.search(rf"\b(?:um|gegen)?\s*dreiviertel\s+{hour_token}\b", text)
        if three_quarter and (hour_value := self._hour_value(three_quarter.group(1), words)):
            hour = hour_value - 1
            if hour <= 0:
                hour = 12
            return f"{hour}:45"
        for word, value in words.items():
            if re.search(rf"\b(?:um|gegen)?\s*{word}\b", text):
                return f"{value}:00"
        return ""

    def _hour_value(self, token: str, words: dict[str, int]) -> int | None:
        if token.isdigit():
            value = int(token)
            return value if 1 <= value <= 24 else None
        return words.get(token)

    def _spoken_date(self, text: str) -> str:
        ordinals = {
            "erster": 1,
            "erste": 1,
            "ersten": 1,
            "zweiter": 2,
            "zweite": 2,
            "zweiten": 2,
            "dritter": 3,
            "dritte": 3,
            "dritten": 3,
            "vierter": 4,
            "vierte": 4,
            "vierten": 4,
            "fuenfter": 5,
            "fuenfte": 5,
            "fuenften": 5,
            "sechster": 6,
            "sechste": 6,
            "sechsten": 6,
            "siebter": 7,
            "siebte": 7,
            "siebten": 7,
            "achter": 8,
            "achte": 8,
            "achten": 8,
            "neunter": 9,
            "neunte": 9,
            "neunten": 9,
            "zehnter": 10,
            "zehnte": 10,
            "zehnten": 10,
            "elfter": 11,
            "elfte": 11,
            "elften": 11,
            "zwoelfter": 12,
            "zwoelfte": 12,
            "zwoelften": 12,
            "fuenfzehnter": 15,
            "fuenfzehnte": 15,
            "fuenfzehnten": 15,
            "zwanzigster": 20,
            "zwanzigste": 20,
            "zwanzigsten": 20,
        }
        month_words = {
            "erster": 1,
            "erste": 1,
            "ersten": 1,
            "zweiter": 2,
            "zweite": 2,
            "zweiten": 2,
            "dritter": 3,
            "dritte": 3,
            "dritten": 3,
            "vierter": 4,
            "vierte": 4,
            "vierten": 4,
            "fuenfter": 5,
            "fuenfte": 5,
            "fuenften": 5,
            "sechster": 6,
            "sechste": 6,
            "sechsten": 6,
            "siebter": 7,
            "siebte": 7,
            "siebten": 7,
            "achter": 8,
            "achte": 8,
            "achten": 8,
            "neunter": 9,
            "neunte": 9,
            "neunten": 9,
            "zehnter": 10,
            "zehnte": 10,
            "zehnten": 10,
            "elfter": 11,
            "elfte": 11,
            "elften": 11,
            "zwoelfter": 12,
            "zwoelfte": 12,
            "zwoelften": 12,
            "januar": 1,
            "februar": 2,
            "maerz": 3,
            "april": 4,
            "mai": 5,
            "juni": 6,
            "juli": 7,
            "august": 8,
            "september": 9,
            "oktober": 10,
            "november": 11,
            "dezember": 12,
        }
        for day_word, day in ordinals.items():
            for month_word, month in month_words.items():
                if re.search(rf"\b{day_word}\s+{month_word}\b", text):
                    return f"{day}.{month}"
        return ""

    def _replace_spoken_digits(self, text: str) -> str:
        text = self._normalize_german(text)
        replacements = {
            "null": "0",
            "eins": "1",
            "ein": "1",
            "zwei": "2",
            "zwo": "2",
            "drei": "3",
            "vier": "4",
            "fuenf": "5",
            "sechs": "6",
            "sieben": "7",
            "acht": "8",
            "neun": "9",
            "zehn": "10",
            "elf": "11",
            "zwoelf": "12",
            "dreizehn": "13",
            "vierzehn": "14",
            "fuenfzehn": "15",
            "sechzehn": "16",
            "siebzehn": "17",
            "achtzehn": "18",
            "neunzehn": "19",
        }
        for word, digit in replacements.items():
            text = re.sub(rf"\b{word}\b", digit, text)
        return text

    def _prefill_appointment_from_text(self, text: str) -> None:
        lower = self._normalize_german(text)
        has_date_or_time_signal = bool(
            re.search(
                r"\b(heute|morgen|uebermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|"
                r"uhr|\d{1,2}\.\d{1,2}|frueh|früh|morgens|vormittag|nachmittag|abend|"
                r"naechste(?:n|r|s)?\s+woche|kommende(?:n|r|s)?\s+"
                r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)|"
                r"diese(?:n|r|s)?\s+(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag))\b",
                lower,
            )
        )
        if has_date_or_time_signal and (not self.state.appointment.date or not self.state.appointment.time):
            self._store_date_time(text)
        if not self.state.appointment.topic:
            if "fotoshooting" in lower or "foto" in lower or "shooting" in lower:
                self.state.appointment.topic = "Fotoshooting"
            elif "video" in lower:
                self.state.appointment.topic = "Video"
            elif "livestream" in lower or "stream" in lower:
                self.state.appointment.topic = "Livestream"

    def _normalize_german(self, text: str) -> str:
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

    def _is_affirmative(self, text: str) -> bool:
        normalized = self._normalize_german(text).strip(" .,!?:;")
        return any(
            re.search(rf"\b{word}\b", normalized)
            for word in ("ja", "jo", "jawohl", "doch", "passt", "genau", "richtig", "okay", "ok", "klar", "stimmt")
        )

    def _is_negative(self, text: str) -> bool:
        normalized = self._normalize_german(text).strip(" .,!?:;")
        return any(re.search(rf"\b{word}\b", normalized) for word in ("nein", "nee", "noe", "nö"))

    def _is_filler_text(self, text: str) -> bool:
        normalized = self._normalize_german(text).strip(" .,!?:;")
        return normalized in {"aeh", "ae", "aehm", "eh", "ehm", "hm", "hmm", "mhm", "mm"}

    def _is_cancel_text(self, text: str) -> bool:
        normalized = self._normalize_german(text)
        return any(
            re.search(rf"\b{word}\b", normalized)
            for word in (
                "abbrechen",
                "abbruch",
                "doch nicht",
                "vergiss",
                "vergessen",
                "egal",
                "lassen",
                "stop",
                "stopp",
            )
        )

    def _next_appointment_question(self) -> str:
        if not self.state.appointment.date:
            self.state.expected_slot = "date_time"
            if self.state.appointment.time:
                return "Danke. An welchem Tag?"
            return "Wann soll der Termin sein?"
        if not self.state.appointment.time:
            self.state.expected_slot = "date_time"
            return "Danke. Um welche Uhrzeit?"
        if not self.state.appointment.topic:
            self.state.expected_slot = "topic"
            return "Worum geht es?"
        if not self.state.appointment.phone:
            self.state.expected_slot = "phone"
            return "Welche Telefonnummer?"
        if not self.state.appointment.confirmed:
            self.state.expected_slot = "confirmed"
            return "Passt das so?"
        self.state.expected_slot = None
        return "Danke. Ich leite weiter."

    def _appointment_summary(self) -> str:
        appt = self.state.appointment
        return (
            f"Termin: Name={appt.name or 'offen'}, Datum={appt.date or 'offen'}, "
            f"Uhrzeit={appt.time or 'offen'}, Thema={appt.topic or 'offen'}, "
            f"Telefon={appt.phone or 'offen'}."
        )


def handle_turn_sync(agent: PhoneAgent, text: str) -> LLMResult:
    return asyncio.run(agent.handle_turn(text))
