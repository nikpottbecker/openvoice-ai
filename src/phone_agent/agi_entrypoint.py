#!/usr/bin/env python3
import logging
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

from .agent import PhoneAgent, handle_turn_sync
from .config import get_settings
from .logging_setup import configure_logging
from .email.mail_service import handle_call_mail
from .simple_agi import AGI
from .stt import transcribe_detailed
from .tts import synthesize

logger = logging.getLogger(__name__)


def _safe_call_id(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)


def _sound_name(path: Path) -> str:
    # Asterisk resolves sounds relative to /var/lib/asterisk/sounds.
    # Our generated files live in the phone-agent subdirectory.
    return f"phone-agent/{path.with_suffix('').name}"


def _record_utterance(agi: AGI, call_id: str, turn: int) -> Path:
    settings = get_settings()
    call_dir = settings.recordings_dir / call_id
    call_dir.mkdir(parents=True, exist_ok=True)
    base = call_dir / f"{call_id}-{turn:02d}"
    min_base = call_dir / f"{call_id}-{turn:02d}-min"
    tail_base = call_dir / f"{call_id}-{turn:02d}-tail"
    start = time.perf_counter()
    min_ms = int(settings.min_record_seconds * 1000)
    total_ms = settings.record_seconds * 1000
    agi.record_file(str(min_base), "wav", "#", min_ms, 0, False, 0)
    agi.record_file(str(tail_base), "wav", "#", max(1000, total_ms - min_ms), 0, False, settings.silence_seconds)
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
    return output


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return 0.0


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


def _play_text(agi: AGI, call_id: str, turn: int, text: str) -> None:
    settings = get_settings()
    output = settings.asterisk_sounds_dir / f"{call_id}-{turn:02d}-reply.wav"
    start = time.perf_counter()
    synthesize(text, output)
    logger.info("timing call_id=%s turn=%s phase=tts seconds=%.3f size=%s", call_id, turn, time.perf_counter() - start, output.stat().st_size)
    start = time.perf_counter()
    agi.stream_file(_sound_name(output))
    logger.info("timing call_id=%s turn=%s phase=playback seconds=%.3f", call_id, turn, time.perf_counter() - start)
    if settings.post_playback_wait_seconds:
        time.sleep(settings.post_playback_wait_seconds)
        logger.info(
            "timing call_id=%s turn=%s phase=post_playback_wait seconds=%.3f",
            call_id,
            turn,
            settings.post_playback_wait_seconds,
        )


def main() -> int:
    configure_logging()
    settings = get_settings()
    agi = AGI()
    call_id = _safe_call_id(agi.env.get("agi_uniqueid", str(int(time.time()))))
    caller_id = agi.env.get("agi_callerid", "unknown")
    agent = PhoneAgent(call_id=call_id, caller_id=caller_id)
    bad_transcripts = 0

    logger.info("call_started call_id=%s caller_id=%s", call_id, caller_id)
    agi.answer()
    _play_text(agi, call_id, 0, agent.greeting())

    for turn in range(1, settings.max_turns + 1):
        recording = _record_utterance(agi, call_id, turn)
        if not recording.exists() or recording.stat().st_size < 2048:
            _play_text(agi, call_id, turn, "Ich konnte leider nichts verstehen. Bitte rufen Sie spaeter erneut an.")
            break

        start = time.perf_counter()
        text, stt_timings = transcribe_detailed(recording)
        logger.info("timing call_id=%s turn=%s phase=stt seconds=%.3f", call_id, turn, time.perf_counter() - start)
        logger.info(
            "timing call_id=%s turn=%s phase=stt_detail recording_duration=%.3f preprocessing=%.3f whisper=%.3f model=%s retry_model=%s retry_whisper=%s",
            call_id,
            turn,
            _wav_duration(recording),
            stt_timings.get("preprocessing", 0),
            stt_timings.get("whisper", 0),
            stt_timings.get("model", ""),
            stt_timings.get("retry_model", ""),
            stt_timings.get("retry_whisper", ""),
        )
        logger.info("transcript_full call_id=%s turn=%s text=%s", call_id, turn, text)
        if _bad_transcript(text):
            bad_transcripts += 1
            if bad_transcripts == 1:
                _play_text(agi, call_id, turn, "Das habe ich nicht gut verstanden. Bitte kurz wiederholen.")
                continue
            _play_text(agi, call_id, turn, "Bitte hinterlassen Sie kurz Ihre Nachricht.")
            message_recording = _record_utterance(agi, call_id, turn + 100)
            logger.info("message_recorded_after_stt_failure call_id=%s path=%s", call_id, message_recording)
            break

        bad_transcripts = 0

        start = time.perf_counter()
        result = handle_turn_sync(agent, text)
        logger.info("timing call_id=%s turn=%s phase=llm seconds=%.3f", call_id, turn, time.perf_counter() - start)
        _play_text(agi, call_id, turn, result.reply)
        if result.should_end_call:
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


def _bad_transcript(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) < 3:
        return True
    filler = {"äh", "hm", "hmm", "ja", "ok", "okay"}
    if cleaned.lower() in filler:
        return True
    if len(cleaned) < 8 and not any(ch.isdigit() for ch in cleaned):
        return True
    return False


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("agi_entrypoint_failed")
        sys.exit(1)
