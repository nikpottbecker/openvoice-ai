from functools import lru_cache
import logging
from pathlib import Path
import subprocess
import time

from faster_whisper import WhisperModel

from .config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _model(model_name: str) -> WhisperModel:
    settings = get_settings()
    return WhisperModel(
        model_name,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe(audio_path: Path) -> str:
    text, _timings = transcribe_detailed(audio_path)
    return text


def transcribe_detailed(audio_path: Path, retry_small: bool = True) -> tuple[str, dict[str, float | str]]:
    settings = get_settings()
    start = time.perf_counter()
    prepared_path = _prepare_audio(audio_path)
    timings: dict[str, float | str] = {
        "preprocessing": round(time.perf_counter() - start, 3),
        "model": settings.whisper_model,
    }

    text, whisper_seconds = _run_whisper(prepared_path, settings.whisper_model)
    timings["whisper"] = round(whisper_seconds, 3)

    if retry_small and settings.whisper_model == "base" and _empty_transcript(text):
        retry_text, retry_seconds = _run_whisper(prepared_path, "small")
        timings["retry_model"] = "small"
        timings["retry_whisper"] = round(retry_seconds, 3)
        if len(retry_text.strip()) > len(text.strip()):
            text = retry_text
            timings["model"] = "small"

    return text.strip(), timings


def _run_whisper(prepared_path: Path, model_name: str) -> tuple[str, float]:
    settings = get_settings()
    start = time.perf_counter()
    try:
        segments, _info = _model(model_name).transcribe(
            str(prepared_path),
            language=settings.whisper_language,
            task="transcribe",
            vad_filter=False,
            condition_on_previous_text=False,
            beam_size=3,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return text.strip(), time.perf_counter() - start
    except Exception:
        logger.exception("whisper_model_failed model=%s", model_name)
        if model_name == "base":
            raise
        return "", time.perf_counter() - start


def _empty_transcript(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    return not cleaned


def _prepare_audio(audio_path: Path) -> Path:
    output = audio_path.with_suffix(".stt.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=80,lowpass=f=3800,loudnorm=I=-16:LRA=6:TP=-1.0,volume=1.8",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return output
