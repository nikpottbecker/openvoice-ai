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
        _resolve_local_model(model_name),
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def _resolve_local_model(model_name: str) -> str:
    model_path = Path(model_name)
    if model_path.exists():
        return str(model_path)

    settings = get_settings()
    app_model_path = settings.app_base_dir / "models" / "whisper" / model_name
    if (app_model_path / "model.bin").exists():
        logger.info("using_app_whisper_snapshot model=%s path=%s", model_name, app_model_path)
        return str(app_model_path)

    repo_by_name = {
        "tiny": "Systran/faster-whisper-tiny",
        "base": "Systran/faster-whisper-base",
        "small": "Systran/faster-whisper-small",
        "medium": "Systran/faster-whisper-medium",
        "large-v3": "Systran/faster-whisper-large-v3",
        "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    }
    repo = repo_by_name.get(model_name)
    if not repo:
        return model_name

    for home in (Path.home(), Path("/root")):
        cache_dir = home / ".cache" / "huggingface" / "hub" / f"models--{repo.replace('/', '--')}"
        ref_path = cache_dir / "refs" / "main"
        if ref_path.exists():
            snapshot = cache_dir / "snapshots" / ref_path.read_text(encoding="utf-8").strip()
            if (snapshot / "model.bin").exists():
                logger.info("using_local_whisper_snapshot model=%s path=%s", model_name, snapshot)
                return str(snapshot)
    return model_name


def transcribe(audio_path: Path) -> str:
    text, _timings = transcribe_detailed(audio_path)
    return text


def warm_default_model() -> None:
    settings = get_settings()
    _model(settings.whisper_model)


def transcribe_detailed(audio_path: Path, retry_small: bool = True) -> tuple[str, dict[str, float | str]]:
    settings = get_settings()
    start = time.perf_counter()
    prepared_path = _prepare_audio(audio_path)
    timings: dict[str, float | str] = {
        "preprocessing": round(time.perf_counter() - start, 3),
        "model": settings.whisper_model,
    }

    text, whisper_seconds, whisper_metrics = _run_whisper(prepared_path, settings.whisper_model)
    timings["whisper"] = round(whisper_seconds, 3)
    timings.update(whisper_metrics)

    if retry_small and settings.whisper_model == "base" and _empty_transcript(text):
        retry_text, retry_seconds, retry_metrics = _run_whisper(prepared_path, "small")
        timings["retry_model"] = "small"
        timings["retry_whisper"] = round(retry_seconds, 3)
        timings["retry_avg_logprob"] = retry_metrics.get("avg_logprob", "")
        timings["retry_no_speech_prob"] = retry_metrics.get("no_speech_prob", "")
        if len(retry_text.strip()) > len(text.strip()):
            text = retry_text
            timings["model"] = "small"

    return text.strip(), timings


def _run_whisper(prepared_path: Path, model_name: str) -> tuple[str, float, dict[str, float | int]]:
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
        segment_list = [segment for segment in segments if segment.text.strip()]
        text = " ".join(segment.text.strip() for segment in segment_list)
        metrics: dict[str, float | int] = {"segments": len(segment_list)}
        if segment_list:
            metrics["avg_logprob"] = round(
                sum(segment.avg_logprob for segment in segment_list) / len(segment_list),
                3,
            )
            metrics["no_speech_prob"] = round(
                max(segment.no_speech_prob for segment in segment_list),
                3,
            )
            metrics["compression_ratio"] = round(
                max(segment.compression_ratio for segment in segment_list),
                3,
            )
        return text.strip(), time.perf_counter() - start, metrics
    except Exception:
        logger.exception("whisper_model_failed model=%s", model_name)
        if model_name == "base":
            raise
        return "", time.perf_counter() - start, {}


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
            "highpass=f=80,lowpass=f=3800,loudnorm=I=-18:LRA=8:TP=-2.0,volume=1.2",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return output
