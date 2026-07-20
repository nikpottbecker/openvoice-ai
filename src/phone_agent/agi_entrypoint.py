#!/usr/bin/env python3
import logging
import math
import os
import subprocess
import sys
import threading
import time
import wave
from array import array
from pathlib import Path

from .agent import PhoneAgent, handle_turn_sync
from .config import get_settings
from .logging_setup import configure_logging
from .email.mail_service import handle_call_mail
from .menu import HybridMenuSession
from .simple_agi import AGI, agi_digit
from .stt import transcribe_detailed, warm_default_model
from .tts import synthesize

logger = logging.getLogger(__name__)


def _safe_call_id(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)


def _sound_name(path: Path) -> str:
    # Asterisk resolves sounds relative to /var/lib/asterisk/sounds.
    # Our generated files live in the phone-agent subdirectory.
    return f"phone-agent/{path.with_suffix('').name}"


def _record_utterance(agi: AGI, call_id: str, turn: int) -> tuple[Path, str]:
    settings = get_settings()
    call_dir = settings.recordings_dir / call_id
    call_dir.mkdir(parents=True, exist_ok=True)
    base = call_dir / f"{call_id}-{turn:02d}"
    min_base = call_dir / f"{call_id}-{turn:02d}-min"
    tail_base = call_dir / f"{call_id}-{turn:02d}-tail"
    start = time.perf_counter()
    min_ms = int(settings.min_record_seconds * 1000)
    total_ms = settings.record_seconds * 1000
    first_digit = agi_digit(agi.record_file(str(min_base), "wav", "#0123456789*", min_ms, 0, False, 0))
    tail_digit = ""
    if not first_digit:
        tail_digit = agi_digit(
            agi.record_file(
                str(tail_base),
                "wav",
                "#0123456789*",
                max(1000, total_ms - min_ms),
                0,
                False,
                settings.silence_seconds,
            )
        )
    output = base.with_suffix(".wav")
    _concat_recordings(min_base.with_suffix(".wav"), tail_base.with_suffix(".wav"), output)
    logger.info(
        "timing call_id=%s turn=%s phase=record seconds=%.3f min_record=%.1f silence=%.1f size=%s",
        call_id,
        turn,
        time.perf_counter() - start,
        settings.min_record_seconds,
        settings.silence_seconds,
        output.stat().st_size if output.exists() else 0,
    )
    logger.info(
        "timing call_id=%s turn=%s phase=recording_audio duration=%.3f",
        call_id,
        turn,
        _wav_duration(output),
    )
    _log_recording_quality(call_id, turn, output)
    return output, first_digit or tail_digit


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return 0.0


def _log_recording_quality(call_id: str, turn: int, path: Path) -> None:
    metrics = _recording_quality(path)
    logger.info(
        "audio_quality call_id=%s turn=%s path=%s sample_rate=%s channels=%s duration=%.3f "
        "rms_dbfs=%s peak_dbfs=%s clipping_percent=%.4f flags=%s",
        call_id,
        turn,
        path,
        metrics.get("sample_rate", ""),
        metrics.get("channels", ""),
        metrics.get("duration_seconds", 0.0),
        metrics.get("rms_dbfs", ""),
        metrics.get("peak_dbfs", ""),
        metrics.get("clipping_percent", 0.0),
        ",".join(metrics.get("flags", [])) or "ok",
    )


def _recording_quality(path: Path) -> dict:
    metrics = {
        "sample_rate": None,
        "channels": None,
        "duration_seconds": 0.0,
        "rms_dbfs": None,
        "peak_dbfs": None,
        "clipping_percent": 0.0,
        "flags": [],
    }
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            metrics["sample_rate"] = wav.getframerate()
            metrics["channels"] = wav.getnchannels()
            metrics["duration_seconds"] = wav.getnframes() / float(wav.getframerate())
            sample_width = wav.getsampwidth()
    except Exception:
        metrics["flags"].append("wav_error")
        return metrics

    if sample_width == 2 and frames:
        samples = array("h")
        samples.frombytes(frames)
        if samples:
            peak = max(abs(sample) for sample in samples)
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            clipped = sum(1 for sample in samples if abs(sample) >= 32760)
            metrics["peak_dbfs"] = _dbfs(peak)
            metrics["rms_dbfs"] = _dbfs(rms)
            metrics["clipping_percent"] = round((clipped / len(samples)) * 100.0, 4)

    flags = metrics["flags"]
    if metrics["duration_seconds"] < 1.0:
        flags.append("very_short_audio")
    if metrics["sample_rate"] not in {8000, 16000}:
        flags.append("unexpected_sample_rate")
    if metrics["channels"] != 1:
        flags.append("not_mono")
    rms_dbfs = metrics["rms_dbfs"]
    if rms_dbfs is None:
        flags.append("digital_silence")
    elif rms_dbfs < -38:
        flags.append("very_low_level")
    elif rms_dbfs > -10:
        flags.append("very_hot_level")
    if metrics["clipping_percent"] > 0.1:
        flags.append("possible_clipping")
    return metrics


def _dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20 * math.log10(value / 32768.0), 3)


def _concat_recordings(first: Path, second: Path, output: Path) -> None:
    inputs = [path for path in (first, second) if path.exists() and path.stat().st_size > 44]
    if not inputs:
        return
    if len(inputs) == 1:
        inputs[0].replace(output)
        return
    concat_list = output.with_suffix(".concat.txt")
    concat_list.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in inputs),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-ar",
            "8000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    concat_list.unlink(missing_ok=True)
    for path in inputs:
        path.unlink(missing_ok=True)


def _play_text(
    agi: AGI,
    call_id: str,
    turn: int,
    text: str,
    escape_digits: str = "",
    audio_suffix: str = "",
) -> str:
    settings = get_settings()
    suffix = f"-{_safe_call_id(audio_suffix)}" if audio_suffix else ""
    output = settings.asterisk_sounds_dir / f"{call_id}-{turn:02d}{suffix}-reply.wav"
    start = time.perf_counter()
    synthesize(text, output)
    logger.info("timing call_id=%s turn=%s phase=tts seconds=%.3f size=%s", call_id, turn, time.perf_counter() - start, output.stat().st_size)
    start = time.perf_counter()
    digit = agi_digit(agi.stream_file(_sound_name(output), escape_digits))
    logger.info("timing call_id=%s turn=%s phase=playback seconds=%.3f", call_id, turn, time.perf_counter() - start)
    if not digit and escape_digits:
        wait_start = time.perf_counter()
        digit = agi_digit(agi.wait_for_digit(1200))
        logger.info(
            "timing call_id=%s turn=%s phase=dtmf_wait seconds=%.3f timeout_ms=1200",
            call_id,
            turn,
            time.perf_counter() - wait_start,
        )
    if settings.post_playback_wait_seconds and not digit:
        time.sleep(settings.post_playback_wait_seconds)
        logger.info(
            "timing call_id=%s turn=%s phase=post_playback_wait seconds=%.3f",
            call_id,
            turn,
            settings.post_playback_wait_seconds,
        )
    if digit:
        logger.info("dtmf_detected call_id=%s turn=%s digit=%s source=playback", call_id, turn, digit)
    return digit


def _play_result_and_process_digits(
    agi: AGI,
    menu: HybridMenuSession,
    call_id: str,
    turn: int,
    result,
) -> bool:
    """Play a reply and immediately consume DTMF barge-in digits from follow-up prompts."""
    current = result
    for depth in range(5):
        digit = _play_text(
            agi,
            call_id,
            turn,
            current.reply,
            "0123456789*#",
            audio_suffix=f"followup-{depth}",
        )
        if current.should_end_call:
            return True
        if not digit:
            return False
        logger.info("dtmf_detected call_id=%s turn=%s digit=%s source=followup", call_id, turn, digit)
        current = menu.handle_slot_dtmf(digit) or menu.handle_dtmf(digit)
    logger.warning("dtmf_followup_limit_reached call_id=%s turn=%s", call_id, turn)
    return False


def main() -> int:
    configure_logging()
    settings = get_settings()
    agi = AGI()
    call_id = _safe_call_id(agi.env.get("agi_uniqueid", str(int(time.time()))))
    caller_id = agi.env.get("agi_callerid", "unknown")
    agent = PhoneAgent(call_id=call_id, caller_id=caller_id)
    menu = HybridMenuSession(agent.state)
    bad_transcripts = 0

    logger.info("call_started call_id=%s caller_id=%s", call_id, caller_id)
    agi.answer()
    _warm_stt_in_background(call_id)
    completed_from_menu = False
    digit = _play_text(agi, call_id, 0, menu.prompt(), "0123456789*#")
    if digit:
        result = menu.handle_dtmf(digit)
        completed_from_menu = _play_result_and_process_digits(agi, menu, call_id, 0, result)

    for turn in range(1, settings.max_turns + 1):
        if completed_from_menu:
            break
        wait_start = time.perf_counter()
        digit = agi_digit(agi.wait_for_digit(250))
        logger.info(
            "timing call_id=%s turn=%s phase=dtmf_wait seconds=%.3f timeout_ms=250",
            call_id,
            turn,
            time.perf_counter() - wait_start,
        )
        if digit:
            logger.info("dtmf_detected call_id=%s turn=%s digit=%s source=pre_record", call_id, turn, digit)
            result = menu.handle_slot_dtmf(digit) or menu.handle_dtmf(digit)
            if _play_result_and_process_digits(agi, menu, call_id, turn, result):
                break
            continue

        recording, record_digit = _record_utterance(agi, call_id, turn)
        if record_digit:
            logger.info("dtmf_detected call_id=%s turn=%s digit=%s source=record", call_id, turn, record_digit)
            result = menu.handle_slot_dtmf(record_digit) or menu.handle_dtmf(record_digit)
            if _play_result_and_process_digits(agi, menu, call_id, turn, result):
                break
            continue
        if not recording.exists() or recording.stat().st_size < 2048:
            _play_text(agi, call_id, turn, "Ich konnte leider nichts verstehen. Bitte rufen Sie spaeter erneut an.")
            break

        start = time.perf_counter()
        text, stt_timings = transcribe_detailed(recording)
        logger.info("timing call_id=%s turn=%s phase=stt seconds=%.3f", call_id, turn, time.perf_counter() - start)
        logger.info(
            "timing call_id=%s turn=%s phase=stt_detail recording_duration=%.3f preprocessing=%.3f whisper=%.3f model=%s avg_logprob=%s no_speech_prob=%s compression_ratio=%s segments=%s retry_model=%s retry_whisper=%s",
            call_id,
            turn,
            _wav_duration(recording),
            stt_timings.get("preprocessing", 0),
            stt_timings.get("whisper", 0),
            stt_timings.get("model", ""),
            stt_timings.get("avg_logprob", ""),
            stt_timings.get("no_speech_prob", ""),
            stt_timings.get("compression_ratio", ""),
            stt_timings.get("segments", ""),
            stt_timings.get("retry_model", ""),
            stt_timings.get("retry_whisper", ""),
        )
        logger.info("transcript_full call_id=%s turn=%s text=%s", call_id, turn, text)
        if _bad_transcript(text, agent.state.expected_slot):
            bad_transcripts += 1
            if bad_transcripts == 1:
                _play_text(agi, call_id, turn, "Das habe ich nicht verstanden. Bitte nochmal kurz.")
                continue
            _play_text(agi, call_id, turn, "Bitte hinterlassen Sie kurz Ihre Nachricht.")
            message_recording, _ = _record_utterance(agi, call_id, turn + 100)
            logger.info("message_recorded_after_stt_failure call_id=%s path=%s", call_id, message_recording)
            break

        bad_transcripts = 0

        start = time.perf_counter()
        result = menu.handle_speech_action(text)
        if result is None:
            result = handle_turn_sync(agent, text)
            if agent.state.expected_slot == "appointment_topic" and agent.state.appointment.topic:
                result = menu.promote_appointment_to_confirmation()
        logger.info("timing call_id=%s turn=%s phase=llm seconds=%.3f", call_id, turn, time.perf_counter() - start)
        if _play_result_and_process_digits(agi, menu, call_id, turn, result):
            break

    try:
        handle_call_mail(agent.state)
    except Exception:
        logger.exception("call_mail_failed call_id=%s", call_id)

    agi.hangup()
    _start_stt_benchmark(call_id)
    logger.info("call_finished call_id=%s", call_id)
    return 0


def _start_stt_benchmark(call_id: str) -> None:
    settings = get_settings()
    log_path = settings.logs_dir / "stt-benchmark.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(settings.app_base_dir / "src")
    try:
        with log_path.open("ab") as log_file:
            subprocess.Popen(
                [sys.executable, "-m", "phone_agent.stt_benchmark", "--call-id", call_id],
                cwd=str(settings.app_base_dir),
                env=env,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
        logger.info("stt_benchmark_started call_id=%s log=%s", call_id, log_path)
    except Exception:
        logger.exception("stt_benchmark_start_failed call_id=%s", call_id)


def _warm_stt_in_background(call_id: str) -> None:
    def run() -> None:
        start = time.perf_counter()
        try:
            warm_default_model()
            logger.info("timing call_id=%s phase=stt_warmup seconds=%.3f", call_id, time.perf_counter() - start)
        except Exception:
            logger.exception("stt_warmup_failed call_id=%s", call_id)

    threading.Thread(target=run, daemon=True).start()


def _bad_transcript(text: str, expected_slot: str | None = None) -> bool:
    cleaned = " ".join(text.strip().split())
    normalized = _normalize_german(cleaned).strip(" .,!?:;")
    if expected_slot in {"confirmed", "appointment_confirm", "callback_confirm"} and normalized in {
        "ja",
        "jo",
        "jawohl",
        "nein",
        "nee",
        "noe",
        "passt",
        "genau",
        "richtig",
        "okay",
        "ok",
        "klar",
        "stimmt",
    }:
        return False
    if len(cleaned) < 3:
        return True
    filler = {"aeh", "ae", "aehm", "eh", "ehm", "hm", "hmm", "mhm", "mm"}
    if normalized in filler:
        return True
    short_slot_values = {
        "name",
        "topic",
        "date_time",
        "phone",
        "appointment_day",
        "appointment_part",
        "appointment_topic",
        "callback_confirm",
        "language",
        "message",
    }
    if expected_slot in short_slot_values and len(cleaned) >= 3:
        return False
    if len(cleaned) < 8 and not any(ch.isdigit() for ch in cleaned):
        return True
    return False


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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("agi_entrypoint_failed")
        sys.exit(1)
