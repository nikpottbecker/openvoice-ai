#!/usr/bin/env python3
import argparse
import gc
import json
import logging
import os
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

import psutil
from faster_whisper import WhisperModel

from .config import get_settings
from .stt import _prepare_audio

logger = logging.getLogger(__name__)


WHISPER_MODELS = ("base", "small", "medium", "large-v3-turbo")


def benchmark_call(call_id: str) -> dict[str, Any]:
    settings = get_settings()
    output_dir = settings.app_base_dir / "stt_benchmarks"
    output_dir.mkdir(parents=True, exist_ok=True)
    wavs = real_call_wavs(call_id)
    result = {
        "call_id": call_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": hardware_info(),
        "engines": [],
        "turns": [],
        "comparison": [],
    }

    for wav in wavs:
        prepared = _prepare_audio(wav)
        turn_result = {
            "original_wav": str(wav),
            "file_size": wav.stat().st_size,
            "duration": wav_duration(wav),
            "prepared_wav": str(prepared),
            "results": [],
        }
        for model_name in WHISPER_MODELS:
            turn_result["results"].append(run_whisper_model(prepared, model_name))
        turn_result["results"].append(run_parakeet_probe())
        turn_result["notes"] = notes_for_turn(turn_result)
        result["turns"].append(turn_result)

    result["comparison"] = build_comparison(result["turns"])
    path = output_dir / f"{call_id}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("stt_benchmark_finished call_id=%s path=%s", call_id, path)
    return result


def run_whisper_model(prepared_wav: Path, model_name: str) -> dict[str, Any]:
    skip = skip_reason(model_name)
    if skip:
        return {"engine": "faster-whisper", "model": model_name, "status": "skipped", "reason": skip}
    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    start = time.perf_counter()
    try:
        model = WhisperModel(model_name, device=get_settings().whisper_device, compute_type=get_settings().whisper_compute_type)
        segments, info = model.transcribe(
            str(prepared_wav),
            language="de",
            task="transcribe",
            vad_filter=False,
            condition_on_previous_text=False,
            beam_size=3,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        runtime = time.perf_counter() - start
        rss_after = proc.memory_info().rss
        del model
        gc.collect()
        return {
            "engine": "faster-whisper",
            "model": model_name,
            "status": "ok",
            "raw_transcript": text.strip(),
            "runtime_seconds": round(runtime, 3),
            "memory_rss_mb_after": round(rss_after / 1024 / 1024, 1),
            "memory_delta_mb": round((rss_after - rss_before) / 1024 / 1024, 1),
            "language_probability": round(getattr(info, "language_probability", 0.0) or 0.0, 3),
            "notes": transcript_notes(text),
        }
    except Exception as exc:
        logger.exception("stt_benchmark_model_failed model=%s wav=%s", model_name, prepared_wav)
        return {
            "engine": "faster-whisper",
            "model": model_name,
            "status": "failed",
            "error": str(exc),
            "runtime_seconds": round(time.perf_counter() - start, 3),
        }


def run_parakeet_probe() -> dict[str, Any]:
    return {
        "engine": "nvidia-parakeet",
        "model": "parakeet",
        "status": "skipped",
        "reason": "not available: NVIDIA /models exposed no speech/parakeet model and local NeMo/Torch is not installed",
    }


def skip_reason(model_name: str) -> str:
    if model_name == "medium":
        mem_gb = psutil.virtual_memory().total / 1024 / 1024 / 1024
        if mem_gb < 4:
            return f"hardware limit: {mem_gb:.1f} GB RAM available, medium benchmark disabled"
    if model_name == "large-v3-turbo":
        mem_gb = psutil.virtual_memory().total / 1024 / 1024 / 1024
        if mem_gb < 6:
            return f"hardware limit: {mem_gb:.1f} GB RAM available, large-v3-turbo benchmark disabled"
    return ""


def build_comparison(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    models = ["base", "small", "medium", "large-v3-turbo", "parakeet"]
    for model in models:
        results = []
        for turn in turns:
            results.extend(
                item for item in turn["results"] if item.get("model") == model or (model == "parakeet" and item.get("engine") == "nvidia-parakeet")
            )
        ok = [item for item in results if item.get("status") == "ok"]
        rows.append(
            {
                "model": model,
                "status": "ok" if ok else (results[0].get("status") if results else "missing"),
                "quality": "needs human reference transcript",
                "avg_runtime_seconds": round(sum(item.get("runtime_seconds", 0) for item in ok) / len(ok), 3) if ok else None,
                "max_memory_mb": max((item.get("memory_rss_mb_after", 0) for item in ok), default=None),
                "empty_transcripts": sum(1 for item in ok if not item.get("raw_transcript")),
                "recommendation_basis": "real WAV benchmark; final quality decision requires manual reference text",
                "reason": results[0].get("reason", "") if results and not ok else "",
            }
        )
    return rows


def transcript_notes(text: str) -> list[str]:
    notes = []
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        notes.append("empty")
    if len(cleaned) < 4:
        notes.append("very_short")
    if any(token in cleaned.lower() for token in ("musik", "untertitel", "applaus")):
        notes.append("possible_hallucination")
    return notes


def notes_for_turn(turn: dict[str, Any]) -> list[str]:
    notes = []
    if turn["duration"] < 1.0:
        notes.append("very_short_audio")
    if turn["file_size"] < 4096:
        notes.append("small_file")
    return notes


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return round(wav.getnframes() / float(wav.getframerate()), 3)
    except Exception:
        return 0.0


def hardware_info() -> dict[str, Any]:
    return {
        "cpu_count": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
        "device": get_settings().whisper_device,
        "compute_type": get_settings().whisper_compute_type,
    }


def latest_real_call_id() -> str | None:
    settings = get_settings()
    ids = []
    for path in settings.recordings_dir.glob("*.wav"):
        if path.name.startswith("sim-") or "-reply" in path.name or ".stt" in path.name:
            continue
        ids.append((path.stat().st_mtime, path.name.split("-", 1)[0]))
    return sorted(ids)[-1][1] if ids else None


def real_call_wavs(call_id: str) -> list[Path]:
    settings = get_settings()
    candidates = list((settings.recordings_dir / call_id).glob(f"{call_id}-*.wav"))
    candidates.extend(settings.recordings_dir.glob(f"{call_id}-*.wav"))
    return sorted(
        {path.resolve() for path in candidates if ".stt" not in path.name and "-reply" not in path.name}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", default="")
    args = parser.parse_args()
    call_id = args.call_id or latest_real_call_id()
    if not call_id:
        raise SystemExit("No real call recordings found")
    result = benchmark_call(call_id)
    print(json.dumps({"call_id": call_id, "comparison": result["comparison"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
