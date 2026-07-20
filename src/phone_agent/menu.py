from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .config import get_settings
from .models import AgentState, LLMResult

logger = logging.getLogger(__name__)


class HybridAction(str, Enum):
    CREATE_APPOINTMENT = "CREATE_APPOINTMENT"
    CHANGE_APPOINTMENT = "CHANGE_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    REQUEST_CALLBACK = "REQUEST_CALLBACK"
    LEAVE_MESSAGE = "LEAVE_MESSAGE"
    GET_INFORMATION = "GET_INFORMATION"
    TRANSFER_CALL = "TRANSFER_CALL"
    CHANGE_LANGUAGE = "CHANGE_LANGUAGE"
    REPEAT_MENU = "REPEAT_MENU"
    GO_BACK = "GO_BACK"
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MenuItem:
    key: str
    action: HybridAction
    label: str
    speech: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class HybridMenuConfig:
    prompt: str
    timeout_prompt: str
    invalid_prompt: str
    max_retries: int
    items: tuple[MenuItem, ...]

    @property
    def dtmf_map(self) -> dict[str, HybridAction]:
        return {item.key: item.action for item in self.items if item.enabled}

    @property
    def speech_map(self) -> dict[HybridAction, tuple[str, ...]]:
        return {item.action: item.speech for item in self.items if item.enabled}


def default_menu_config() -> HybridMenuConfig:
    return HybridMenuConfig(
        prompt=(
            "Fuer Termin 1 oder Termin sagen. Fuer Rueckruf 4. "
            "Fuer Nachricht 5. Fuer Infos 6. Fuer Mitarbeiter 7."
        ),
        timeout_prompt="Keine Eingabe erkannt. Druecken Sie 9 fuer das Menue oder 7 fuer Mitarbeiter.",
        invalid_prompt="Diese Auswahl ist nicht verfuegbar. Bitte 1 bis 7 oder 9 druecken.",
        max_retries=2,
        items=(
            MenuItem("1", HybridAction.CREATE_APPOINTMENT, "Termin vereinbaren", ("termin", "buchen", "vereinbaren")),
            MenuItem("2", HybridAction.CHANGE_APPOINTMENT, "Termin aendern", ("verschieben", "aendern", "andern")),
            MenuItem("3", HybridAction.CANCEL_APPOINTMENT, "Termin absagen", ("absagen", "stornieren")),
            MenuItem("4", HybridAction.REQUEST_CALLBACK, "Rueckruf anfordern", ("rueckruf", "ruckruf", "zurueckrufen")),
            MenuItem("5", HybridAction.LEAVE_MESSAGE, "Nachricht hinterlassen", ("nachricht", "anfrage", "mitteilung")),
            MenuItem("6", HybridAction.GET_INFORMATION, "Informationen", ("oeffnungszeiten", "offnungszeiten", "adresse", "info")),
            MenuItem("7", HybridAction.TRANSFER_CALL, "Mitarbeiter", ("mitarbeiter", "verbinden", "weiterleitung")),
            MenuItem("8", HybridAction.CHANGE_LANGUAGE, "Sprache", ("sprache", "englisch", "niederlaendisch")),
            MenuItem("9", HybridAction.REPEAT_MENU, "Menue wiederholen", ("wiederholen", "menue")),
            MenuItem("0", HybridAction.GO_BACK, "Hilfe oder Hauptmenue", ("hilfe", "zurueck", "zuruck")),
            MenuItem("*", HybridAction.GO_BACK, "Zurueck", ("zurueck", "zuruck")),
            MenuItem("#", HybridAction.CONFIRM, "Bestaetigen", ("bestaetigen", "fertig")),
        ),
    )


def load_menu_config(path: Path | None = None) -> HybridMenuConfig:
    settings = get_settings()
    config_path = path or settings.config_dir / "phone_menu.json"
    if not config_path.exists():
        return default_menu_config()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        defaults = default_menu_config()
        items = tuple(
            MenuItem(
                key=str(item["key"]),
                action=HybridAction(item["action"]),
                label=str(item["label"]),
                speech=tuple(str(value) for value in item.get("speech", ())),
                enabled=bool(item.get("enabled", True)),
            )
            for item in raw.get("items", [])
        )
        return HybridMenuConfig(
            prompt=str(raw.get("prompt") or defaults.prompt),
            timeout_prompt=str(raw.get("timeout_prompt") or defaults.timeout_prompt),
            invalid_prompt=str(raw.get("invalid_prompt") or defaults.invalid_prompt),
            max_retries=int(raw.get("max_retries") or defaults.max_retries),
            items=items or defaults.items,
        )
    except Exception:
        logger.exception("phone_menu_config_invalid path=%s", config_path)
        return default_menu_config()


def action_from_dtmf(digit: str, config: HybridMenuConfig | None = None) -> HybridAction:
    if not digit:
        return HybridAction.UNKNOWN
    menu = config or load_menu_config()
    return menu.dtmf_map.get(digit.strip(), HybridAction.UNKNOWN)


def action_from_speech(text: str, config: HybridMenuConfig | None = None) -> HybridAction:
    normalized = _normalize(text)
    if not normalized:
        return HybridAction.UNKNOWN
    direct_patterns = (
        (HybridAction.CANCEL_APPOINTMENT, r"\b(absagen|stornieren|loeschen)\b"),
        (HybridAction.CHANGE_APPOINTMENT, r"\b(verschieben|aendern|andern|umbuchen)\b"),
        (HybridAction.REQUEST_CALLBACK, r"\b(rueckruf|ruckruf|zurueck|zuruck|rufen)\b"),
        (HybridAction.GET_INFORMATION, r"\b(oeffnungszeit|offnungszeit|geoeffnet|geoffnet|adresse|info)\b"),
        (HybridAction.TRANSFER_CALL, r"\b(mitarbeiter|verbinden|weiterleitung|person)\b"),
        (HybridAction.CHANGE_LANGUAGE, r"\b(sprache|englisch|niederlaendisch|niederlandisch)\b"),
        (HybridAction.LEAVE_MESSAGE, r"\b(nachricht|mitteilung|anfrage)\b"),
        (HybridAction.CREATE_APPOINTMENT, r"\b(termin|buchen|vereinbaren)\b"),
    )
    for action, pattern in direct_patterns:
        if re.search(pattern, normalized):
            return action
    menu = config or load_menu_config()
    best_action = HybridAction.UNKNOWN
    best_score = 0
    for action, phrases in menu.speech_map.items():
        for phrase in phrases:
            score = _phrase_score(normalized, _normalize(phrase))
            if score > best_score:
                best_action = action
                best_score = score
    return best_action if best_score >= 1 else HybridAction.UNKNOWN


@dataclass
class HybridMenuSession:
    state: AgentState
    config: HybridMenuConfig = field(default_factory=load_menu_config)
    menu_level: str = "main"
    retries: int = 0

    def prompt(self) -> str:
        return self.config.prompt

    def handle_dtmf(self, digit: str) -> LLMResult:
        action = action_from_dtmf(digit, self.config)
        return self.handle_action(action, source="dtmf", raw=digit)

    def handle_speech_action(self, text: str) -> LLMResult | None:
        slot_result = self.handle_slot_speech(text)
        if slot_result:
            return slot_result
        action = action_from_speech(text, self.config)
        if action == HybridAction.UNKNOWN:
            return None
        return self.handle_action(action, source="speech", raw=text)

    def handle_action(self, action: HybridAction, source: str, raw: str = "") -> LLMResult:
        logger.info(
            "hybrid_menu_action call_id=%s source=%s raw=%s action=%s level=%s",
            self.state.call_id,
            source,
            _mask_dtmf(raw) if source == "dtmf" else raw,
            action.value,
            self.menu_level,
        )
        if action == HybridAction.CREATE_APPOINTMENT:
            self._reset_retries()
            self.state.intent = "appointment"
            self.state.expected_slot = "appointment_day"
            self.menu_level = "appointment_day"
            return self._reply("Termin. Druecken Sie 1 Montag bis 5 Freitag, oder 6 fuer schnellstmoeglich.")
        if action == HybridAction.CHANGE_APPOINTMENT:
            self._reset_retries()
            self.state.intent = "appointment"
            self.state.expected_slot = "message"
            self.menu_level = "change_appointment"
            return self._reply("Termin aendern. Bitte nennen Sie kurz Name, bisherigen Termin und Wunschzeit.")
        if action == HybridAction.CANCEL_APPOINTMENT:
            self._reset_retries()
            self.state.intent = "appointment"
            self.state.expected_slot = "message"
            self.menu_level = "cancel_appointment"
            return self._reply("Termin absagen. Bitte nennen Sie kurz Name und Termin.")
        if action == HybridAction.REQUEST_CALLBACK:
            self._reset_retries()
            self.state.intent = "callback"
            self.state.expected_slot = "callback_confirm"
            self.menu_level = "callback_confirm"
            return self._reply("Rueckruf an diese Nummer? Druecken Sie 1 fuer Ja oder 2 fuer andere Nummer.")
        if action == HybridAction.LEAVE_MESSAGE:
            self._reset_retries()
            self.state.intent = "message"
            self.state.expected_slot = "message"
            self.menu_level = "message"
            return self._reply("Bitte sprechen Sie Ihre Nachricht nach dem Ton.")
        if action == HybridAction.GET_INFORMATION:
            self._reset_retries()
            return self._reply("Informationen sind noch nicht hinterlegt. Ich leite die Anfrage an Nik weiter.")
        if action == HybridAction.TRANSFER_CALL:
            self._reset_retries()
            return self._reply("Ich notiere den Wunsch nach Rueckmeldung und leite ihn an Nik weiter.", end=True)
        if action == HybridAction.CHANGE_LANGUAGE:
            self._reset_retries()
            self.state.expected_slot = "language"
            self.menu_level = "language"
            return self._reply("Sprache: 1 Deutsch, 2 Englisch, 3 Niederlaendisch.")
        if action == HybridAction.REPEAT_MENU:
            self._reset_retries()
            self.menu_level = "main"
            self.state.expected_slot = None
            return self._reply(self.config.prompt)
        if action in {HybridAction.GO_BACK, HybridAction.CANCEL}:
            self._reset_retries()
            self.menu_level = "main"
            self.state.expected_slot = None
            return self._reply(self.config.prompt)
        return self._invalid()

    def handle_slot_dtmf(self, digit: str) -> LLMResult | None:
        slot = self.state.expected_slot
        if not slot:
            return self.handle_dtmf(digit)
        if digit in {"0", "*"}:
            self._reset_retries()
            self.menu_level = "main"
            self.state.expected_slot = None
            return self._reply(self.config.prompt)
        if digit == "9":
            self._reset_retries()
            return self._reply(self._slot_prompt(slot))

        if slot == "appointment_day":
            days = {"1": "Montag", "2": "Dienstag", "3": "Mittwoch", "4": "Donnerstag", "5": "Freitag", "6": "naechstmoeglich"}
            if digit in days:
                self._reset_retries()
                self.state.appointment.date = days[digit]
                self.state.expected_slot = "appointment_part"
                self.menu_level = "appointment_part"
                return self._reply("Wann passt es? 1 Vormittag, 2 Nachmittag, 3 fruehester Termin.")
            return self._invalid()

        if slot == "appointment_part":
            parts = {"1": "vormittags", "2": "nachmittags", "3": "fruehester Termin"}
            if digit in parts:
                self._reset_retries()
                self.state.appointment.time = parts[digit]
                self.state.expected_slot = "appointment_topic"
                self.menu_level = "appointment_topic"
                return self._reply("Worum geht es? Sagen Sie kurz das Thema.")
            return self._invalid()

        if slot == "confirmed":
            if digit in {"1", "#"}:
                self._reset_retries()
                self.state.appointment.confirmed = True
                self.state.expected_slot = None
                self.menu_level = "done"
                return self._reply("Danke. Ich leite die Terminanfrage an Nik weiter.", end=True)
            if digit == "2":
                self._reset_retries()
                self.state.expected_slot = "appointment_day"
                self.menu_level = "appointment_day"
                return self._reply("Okay. Neuer Tag: 1 Montag bis 5 Freitag, oder 6 schnellstmoeglich.")
            return self._invalid()

        if slot == "callback_confirm":
            if digit == "1":
                self._reset_retries()
                self.state.expected_slot = None
                self.menu_level = "done"
                return self._reply("Danke. Ich leite den Rueckruf an Nik weiter.", end=True)
            if digit == "2":
                self._reset_retries()
                self.state.expected_slot = "phone"
                self.menu_level = "callback_phone"
                return self._reply("Bitte sprechen Sie die andere Telefonnummer.")
            return self._invalid()

        if slot == "language":
            languages = {"1": "Deutsch", "2": "Englisch", "3": "Niederlaendisch"}
            if digit in languages:
                self._reset_retries()
                self.state.summary = f"Sprache: {languages[digit]}"
                self.state.expected_slot = None
                self.menu_level = "main"
                return self._reply(self.config.prompt)
            return self._invalid()

        return None

    def handle_slot_speech(self, text: str) -> LLMResult | None:
        slot = self.state.expected_slot
        normalized = _normalize(text).strip()
        if not slot or not normalized:
            return None
        logger.info(
            "hybrid_menu_slot_speech call_id=%s slot=%s text=%s level=%s",
            self.state.call_id,
            slot,
            text,
            self.menu_level,
        )
        if slot == "appointment_day":
            day = _day_from_speech(normalized)
            if day:
                self._reset_retries()
                self.state.appointment.date = day
                appointment_part = _appointment_part_from_speech(normalized)
                if appointment_part:
                    self.state.appointment.time = appointment_part
                    topic = _topic_from_speech(text)
                    if topic:
                        self.state.appointment.topic = topic
                        return self.promote_appointment_to_confirmation()
                    self.state.expected_slot = "appointment_topic"
                    self.menu_level = "appointment_topic"
                    return self._reply("Worum geht es? Sagen Sie kurz das Thema.")
                self.state.expected_slot = "appointment_part"
                self.menu_level = "appointment_part"
                return self._reply("Wann passt es? 1 Vormittag, 2 Nachmittag, 3 fruehester Termin.")
            return None
        if slot == "appointment_part":
            self.state.appointment.time = _appointment_part_from_speech(normalized) or self.state.appointment.time
            if self.state.appointment.time:
                self._reset_retries()
                self.state.expected_slot = "appointment_topic"
                self.menu_level = "appointment_topic"
                return self._reply("Worum geht es? Sagen Sie kurz das Thema.")
            return None
        if slot == "appointment_topic":
            self._reset_retries()
            self.state.appointment.topic = text.strip(" .,;:") or "Termin"
            return self.promote_appointment_to_confirmation()
        if slot == "callback_confirm":
            if any(word in normalized for word in ("ja", "passt", "richtig", "genau", "stimmt", "okay", "ok", "klar")):
                self._reset_retries()
                self.state.expected_slot = None
                self.menu_level = "done"
                return self._reply("Danke. Ich leite den Rueckruf an Nik weiter.", end=True)
            if any(word in normalized for word in ("nein", "andere", "andern", "aendern")):
                self._reset_retries()
                self.state.expected_slot = "phone"
                self.menu_level = "callback_phone"
                return self._reply("Bitte sprechen Sie die andere Telefonnummer.")
            return None
        if slot == "phone" and self.state.intent == "callback":
            phone = _clean_phone_text(text)
            if phone:
                self._reset_retries()
                self.state.summary = f"Rueckrufnummer: {phone}"
                self.state.expected_slot = None
                self.menu_level = "done"
                return self._reply("Danke. Ich leite den Rueckruf an Nik weiter.", end=True)
            return self._reply("Welche Telefonnummer?")
        if slot == "message":
            self._reset_retries()
            self.state.summary = text.strip()[:600]
            self.state.expected_slot = None
            self.menu_level = "done"
            return self._reply("Danke. Ich leite die Nachricht an Nik weiter.", end=True)
        if slot == "confirmed":
            if any(word in normalized for word in ("ja", "passt", "richtig", "genau", "stimmt", "okay", "ok")):
                self._reset_retries()
                self.state.appointment.confirmed = True
                self.state.expected_slot = None
                self.menu_level = "done"
                return self._reply("Danke. Ich leite die Terminanfrage an Nik weiter.", end=True)
            if any(word in normalized for word in ("nein", "aendern", "andern", "falsch")):
                self._reset_retries()
                self.state.expected_slot = "appointment_day"
                self.menu_level = "appointment_day"
                return self._reply("Okay. Neuer Tag: 1 Montag bis 5 Freitag, oder 6 schnellstmoeglich.")
            return None
        return None

    def promote_appointment_to_confirmation(self) -> LLMResult:
        appt = self.state.appointment
        if not appt.name:
            appt.name = "wird spaeter geklaert"
        if not appt.topic:
            appt.topic = "Termin"
        if not appt.phone and self.state.caller_id not in {"", "unknown", "anonymous"}:
            appt.phone = self.state.caller_id
        self.state.expected_slot = "confirmed"
        self.menu_level = "appointment_confirm"
        return self._reply(
            f"Termin {appt.date or 'offen'} {appt.time or ''} wegen {appt.topic}. "
            "Druecken Sie 1 zum Bestaetigen oder 2 zum Aendern."
        )

    def _reply(self, text: str, end: bool = False) -> LLMResult:
        return LLMResult(
            reply=text,
            intent=self.state.intent,
            appointment=self.state.appointment,
            summary=self.state.summary,
            should_end_call=end,
            action={"menu_level": self.menu_level},
        )

    def _invalid(self) -> LLMResult:
        self.retries += 1
        if self.retries >= self.config.max_retries:
            return self._reply("Ich konnte die Auswahl nicht zuordnen. Ich leite es an Nik weiter.", end=True)
        return self._reply(self.config.invalid_prompt)

    def _reset_retries(self) -> None:
        self.retries = 0

    def _slot_prompt(self, slot: str) -> str:
        prompts = {
            "appointment_day": "1 Montag, 2 Dienstag, 3 Mittwoch, 4 Donnerstag, 5 Freitag, 6 schnellstmoeglich.",
            "appointment_part": "1 Vormittag, 2 Nachmittag, 3 fruehester Termin.",
            "appointment_topic": "Bitte sprechen Sie kurz das Thema.",
            "confirmed": "Druecken Sie 1 zum Bestaetigen oder 2 zum Aendern.",
            "callback_confirm": "1 fuer Rueckruf an diese Nummer, 2 fuer andere Nummer.",
            "language": "1 Deutsch, 2 Englisch, 3 Niederlaendisch.",
        }
        return prompts.get(slot, self.config.prompt)


def _normalize(text: str) -> str:
    return (
        text.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _phrase_score(text: str, phrase: str) -> int:
    if not phrase:
        return 0
    if phrase in text:
        return 2
    phrase_tokens = set(re.findall(r"[a-z0-9]+", phrase))
    text_tokens = set(re.findall(r"[a-z0-9]+", text))
    return len(phrase_tokens & text_tokens)


def _mask_dtmf(value: str) -> str:
    if len(value) <= 1:
        return value
    return value[:1] + "*" * (len(value) - 1)


def _day_from_speech(text: str) -> str:
    days = {
        "montag": "Montag",
        "dienstag": "Dienstag",
        "mittwoch": "Mittwoch",
        "donnerstag": "Donnerstag",
        "freitag": "Freitag",
    }
    for word, label in days.items():
        if word in text:
            return label
    if any(word in text for word in ("schnell", "egal", "naechst", "nächst")):
        return "naechstmoeglich"
    return ""


def _appointment_part_from_speech(text: str) -> str:
    if any(word in text for word in ("vormittag", "morgens", "frueh")):
        return "vormittags"
    if any(word in text for word in ("nachmittag", "abends", "spaet")):
        return "nachmittags"
    if any(word in text for word in ("fruehest", "egal", "schnell")):
        return "fruehester Termin"
    return ""


def _topic_from_speech(text: str) -> str:
    normalized = _normalize(text)
    if "fotoshooting" in normalized or "foto" in normalized or "shooting" in normalized:
        return "Fotoshooting"
    if "video" in normalized:
        return "Video"
    if "livestream" in normalized or "stream" in normalized:
        return "Livestream"
    return ""


def _clean_phone_text(text: str) -> str:
    normalized = _replace_spoken_digits(_normalize(text))
    normalized = re.sub(r"\bplus\s+", "+", normalized)
    cleaned = re.sub(r"[^\d+]", "", normalized)
    digit_count = len(re.sub(r"\D", "", cleaned))
    return cleaned if digit_count >= 5 else ""


def _replace_spoken_digits(text: str) -> str:
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
