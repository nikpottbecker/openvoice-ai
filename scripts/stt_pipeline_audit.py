#!/usr/bin/env python3
"""Benchmark the STT pipeline on real call recordings without changing runtime behavior."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil
from faster_whisper import WhisperModel


@dataclass(frozen=True)
class PrepVariant:
    name: str
    ffmpeg_filter: str


@dataclass(frozen=True)
class WhisperVariant:
    model: str
    beam_size: int


PREP_VARIANTS = (
    PrepVariant("current", "highpass=f=80,lowpass=f=3800,loudnorm=I=-16:LRA=6:TP=-1.0,volume=1.8"),
    PrepVariant("normalize_only", "loudnorm=I=-18:LRA=8:TP=-2.0"),
    PrepVariant("telephone_band_soft", "highpass=f=70,lowpass=f=3900,loudnorm=I=-18:LRA=8:TP=-2.0"),
    PrepVariant("no_loudnorm", "highpass=f=70,lowpass=f=3900,volume=2.0"),
)

WHISPER_VARIANTS = (
    WhisperVariant("base", 1),
    WhisperVariant("base", 3),
    WhisperVariant("small", 1),
    WhisperVariant("small", 3),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default="/opt/phone-agent")
    parser.add_argument("--call-id", action="append", default=[])
    parser.add_argument("--limit-turns", type=int, default=0)
    parser.add_argument("--include-medium", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    call_ids = args.call_id or latest_call_ids(app_dir, limit=2)
    whisper_variants = list(WHISPER_VARIANTS)
    if args.include_medium:
        whisper_variants.append(WhisperVariant("medium", 1))

    output = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app_dir": str(app_dir),
        "hardware": hardware_info(),
        "prep_variants": [variant.__dict__ for variant in PREP_VARIANTS],
        "whisper_variants": [variant.__dict__ for variant in whisper_variants],
        "calls": [],
        "summary": [],
    }

    for call_id in call_ids:
        wavs = real_call_wavs(app_dir, call_id)
        if args.limit_turns:
            wavs = wavs[: args.limit_turns]
        output["calls"].append(audit_call(app_dir, call_id, wavs, whisper_variants))

    output["summary"] = summarize(output["calls"])
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


def latest_call_ids(app_dir: Path, limit: int) -> list[str]:
    recordings = app_dir / "recordings"
    dirs = sorted(recordings.glob("[0-9]*_*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.name for path in dirs[:limit]]


def real_call_wavs(app_dir: Path, call_id: str) -> list[Path]:
    call_dir = app_dir / "recordings" / call_id
    return sorted(
        path
        for path in call_dir.glob(f"{call_id}-*.wav")
        if ".stt" not in path.name and "-reply" not in path.name and "-min" not in path.name and "-tail" not in path.name
    )


def audit_call(app_dir: Path, call_id: str, wavs: list[Path], whisper_variants: list[WhisperVariant]) -> dict[str, Any]:
    model_cache: dict[str, WhisperModel] = {}
    call_result: dict[str, Any] = {"call_id": call_id, "turns": []}
    work_dir = app_dir / "stt_audits" / call_id
    work_dir.mkdir(parents=True, exist_ok=True)

    for wav in wavs:
        turn: dict[str, Any] = {
            "wav": str(wav),
            "file_size": wav.stat().st_size,
            "audio": audio_metrics(wav),
            "variants": [],
        }
        for prep in PREP_VARIANTS:
            prepared = work_dir / f"{wav.stem}.{prep.name}.wav"
            prep_seconds = prepare_audio(wav, prepared, prep.ffmpeg_filter)
            prep_result: dict[str, Any] = {
                "prep": prep.name,
                "prep_seconds": prep_seconds,
                "prepared_audio": audio_metrics(prepared),
                "transcripts": [],
            }
            for whisper in whisper_variants:
                prep_result["transcripts"].append(run_whisper(prepared, whisper, model_cache))
            turn["variants"].append(prep_result)
        call_result["turns"].append(turn)
    return call_result


def prepare_audio(source: Path, target: Path, audio_filter: str) -> float:
    start = time.perf_counter()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            audio_filter,
            str(target),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return round(time.perf_counter() - start, 3)


def run_whisper(path: Path, variant: WhisperVariant, model_cache: dict[str, WhisperModel]) -> dict[str, Any]:
    model = model_cache.get(variant.model)
    load_seconds = 0.0
    if model is None:
        start_load = time.perf_counter()
        model = WhisperModel(variant.model, device="cpu", compute_type="int8")
        model_cache[variant.model] = model
        load_seconds = time.perf_counter() - start_load

    start = time.perf_counter()
    segments, info = model.transcribe(
        str(path),
        language="de",
        task="transcribe",
        vad_filter=False,
        condition_on_previous_text=False,
        beam_size=variant.beam_size,
    )
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return {
        "model": variant.model,
        "beam_size": variant.beam_size,
        "load_seconds": round(load_seconds, 3),
        "runtime_seconds": round(time.perf_counter() - start, 3),
        "language_probability": round(getattr(info, "language_probability", 0.0) or 0.0, 3),
        "raw_transcript": text.strip(),
        "notes": transcript_notes(text),
    }


def audio_metrics(path: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return metrics
    try:
        with wave.open(str(path), "rb") as wav:
            metrics.update(
                {
                    "channels": wav.getnchannels(),
                    "sample_rate": wav.getframerate(),
                    "sample_width": wav.getsampwidth(),
                    "frames": wav.getnframes(),
                    "duration_seconds": round(wav.getnframes() / float(wav.getframerate()), 3),
                }
            )
    except Exception as exc:
        metrics["wave_error"] = str(exc)

    vol = run_ffmpeg_filter(path, "volumedetect")
    for key in ("mean_volume", "max_volume"):
        match = re.search(key + r":\s*([-0-9.]+) dB", vol)
        if match:
            metrics[key + "_db"] = float(match.group(1))

    sil = run_ffmpeg_filter(path, "silencedetect=noise=-35dB:d=0.2")
    starts = [float(item) for item in re.findall(r"silence_start: ([0-9.]+)", sil)]
    ends = [float(item) for item in re.findall(r"silence_end: ([0-9.]+)", sil)]
    metrics["silence_events"] = len(starts)
    metrics["first_silence_start"] = starts[0] if starts else None
    metrics["last_silence_end"] = ends[-1] if ends else None
    return metrics


def run_ffmpeg_filter(path: Path, audio_filter: str) -> str:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", audio_filter, "-f", "null", "-"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout + proc.stderr


def transcript_notes(text: str) -> list[str]:
    notes = []
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        notes.append("empty")
    if len(cleaned) < 4:
        notes.append("very_short")
    if any(token in cleaned.lower() for token in ("untertitel", "applaus", "musik")):
        notes.append("possible_hallucination")
    return notes


def summarize(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for call in calls:
        for turn in call["turns"]:
            for variant in turn["variants"]:
                for transcript in variant["transcripts"]:
                    key = (variant["prep"], transcript["model"], transcript["beam_size"])
                    rows.setdefault(key, []).append(transcript)

    summary = []
    for (prep, model, beam), transcripts in sorted(rows.items()):
        summary.append(
            {
                "prep": prep,
                "model": model,
                "beam_size": beam,
                "avg_runtime_seconds": round(
                    sum(item["runtime_seconds"] for item in transcripts) / len(transcripts), 3
                ),
                "empty_transcripts": sum(1 for item in transcripts if not item["raw_transcript"]),
                "hallucination_flags": sum(
                    1 for item in transcripts if "possible_hallucination" in item["notes"]
                ),
            }
        )
    return summary


def hardware_info() -> dict[str, Any]:
    return {
        "cpu_count": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
    }


if __name__ == "__main__":
    raise SystemExit(main())
