from pathlib import Path
import wave
from array import array

from phone_agent.agi_entrypoint import _bad_transcript, _play_text, _recording_quality


class FakeAGI:
    def __init__(self) -> None:
        self.streamed: list[str] = []

    def stream_file(self, filename: str, escape_digits: str = "") -> str:
        self.streamed.append(filename)
        return "200 result=0"

    def wait_for_digit(self, timeout_ms: int) -> str:
        return "200 result=0"


def test_confirmation_yes_with_punctuation_is_not_bad() -> None:
    assert _bad_transcript("Ja!", expected_slot="confirmed") is False


def test_colloquial_confirmations_are_not_bad_in_confirmation_slot() -> None:
    for text in ("jo", "klar", "stimmt", "nee", "noe"):
        assert _bad_transcript(text, expected_slot="confirmed") is False


def test_short_answers_are_allowed_in_appointment_confirm_slot() -> None:
    for text in ("ja", "nein", "passt", "stimmt"):
        assert _bad_transcript(text, expected_slot="appointment_confirm") is False


def test_short_yes_outside_confirmation_still_needs_context() -> None:
    assert _bad_transcript("Ja!", expected_slot=None) is True


def test_filler_is_bad() -> None:
    assert _bad_transcript("äh", expected_slot="topic") is True
    assert _bad_transcript("ähm", expected_slot="name") is True
    assert _bad_transcript("mhm", expected_slot="topic") is True


def test_short_slot_answers_are_allowed_in_expected_context() -> None:
    assert _bad_transcript("Nik", expected_slot="name") is False
    assert _bad_transcript("Uwe", expected_slot="name") is False
    assert _bad_transcript("Foto", expected_slot="topic") is False
    assert _bad_transcript("Montag", expected_slot="date_time") is False


def test_short_hybrid_menu_slot_answers_are_allowed_in_expected_context() -> None:
    assert _bad_transcript("Foto", expected_slot="appointment_topic") is False
    assert _bad_transcript("Morgen", expected_slot="appointment_day") is False
    assert _bad_transcript("frueh", expected_slot="appointment_part") is False
    assert _bad_transcript("Ja", expected_slot="callback_confirm") is False


def test_play_text_uses_audio_suffix_without_changing_timing_turn(monkeypatch, tmp_path) -> None:
    from phone_agent import agi_entrypoint

    class Settings:
        asterisk_sounds_dir = tmp_path
        post_playback_wait_seconds = 0

    def fake_synthesize(text: str, output: Path) -> None:
        output.write_bytes(b"RIFFxxxxWAVE")

    monkeypatch.setattr(agi_entrypoint, "get_settings", lambda: Settings())
    monkeypatch.setattr(agi_entrypoint, "synthesize", fake_synthesize)
    agi = FakeAGI()

    _play_text(agi, "call1", 2, "Hallo", audio_suffix="followup-1")

    assert agi.streamed == ["phone-agent/call1-02-followup-1-reply"]
    assert (tmp_path / "call1-02-followup-1-reply.wav").exists()


def test_recording_quality_flags_silence_and_short_audio(tmp_path) -> None:
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 400)

    metrics = _recording_quality(wav_path)

    assert metrics["rms_dbfs"] is None
    assert "digital_silence" in metrics["flags"]
    assert "very_short_audio" in metrics["flags"]


def test_recording_quality_flags_clipping(tmp_path) -> None:
    wav_path = tmp_path / "clipping.wav"
    samples = array("h", [0, 32767, -32768, 1000, -1000] * 2000)
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())

    metrics = _recording_quality(wav_path)

    assert metrics["peak_dbfs"] == 0.0
    assert metrics["clipping_percent"] > 0
    assert "possible_clipping" in metrics["flags"]
