#!/usr/bin/env python3
"""Generate comparable TTS voice samples and technical metrics for phone audio."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
import urllib.request
import wave
from array import array
from pathlib import Path
from typing import Any

import psutil

from phone_agent.config import get_settings
from phone_agent.tts import _run_piper, convert_for_asterisk
from phone_agent.tts_config import TTSConfig, available_tts_voices


TEST_TEXTS = [
    "Guten Tag und herzlich willkommen bei OpenVoice AI. Wie kann ich Ihnen helfen?",
    "Für einen neuen Termin drücken Sie bitte die 1 oder sagen Sie Termin.",
    "Ich habe Mittwoch, den 22. Juli, um 15 Uhr verstanden. Drücken Sie die 1 zur Bestätigung.",
    "Darf ich bitte noch Ihren vollständigen Namen erfahren?",
    "Ich habe den Namen Nik Pottbecker verstanden. Ist das korrekt?",
    "Einen kleinen Moment bitte, ich prüfe die verfügbaren Termine.",
    "Vielen Dank für Ihren Anruf. Auf Wiederhören.",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default="")
    parser.add_argument("--voices", nargs="*", default=[])
    parser.add_argument("--output", default="")
    parser.add_argument("--download-missing", action="store_true")
    parser.add_argument("--length-scale", type=float, default=1.0)
    parser.add_argument("--sentence-silence", type=float, default=0.22)
    parser.add_argument("--volume", type=float, default=1.0)
    args = parser.parse_args()

    if args.app_dir:
        import os

        os.environ["APP_BASE_DIR"] = args.app_dir
        from phone_agent.config import get_settings as cached_settings

        cached_settings.cache_clear()

    voices = args.voices or [
        "de_DE-thorsten-medium",
        "de_DE-thorsten-high",
        "de_DE-thorsten_emotional-medium",
        "de_DE-mls-medium",
        "de_DE-kerstin-low",
        "de_DE-karlsson-low",
        "de_DE-ramona-low",
    ]
    settings = get_settings()
    run_dir = Path(args.output) if args.output else settings.app_base_dir / "tts_voice_comparison" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app_dir": str(settings.app_base_dir),
        "piper_bin": str(settings.piper_bin),
        "hardware": {
            "cpu_count": psutil.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
        },
        "test_texts": TEST_TEXTS,
        "voices": [],
        "recommendation": None,
    }

    for voice_id in voices:
        voice_report = benchmark_voice(
            voice_id,
            run_dir,
            download_missing=args.download_missing,
            length_scale=args.length_scale,
            sentence_silence=args.sentence_silence,
            volume=args.volume,
        )
        report["voices"].append(voice_report)

    report["recommendation"] = recommend_voice(report["voices"])
    report_path = run_dir / "tts_voice_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(report, run_dir / "README.md")
    print(json.dumps({"output": str(run_dir), "report": str(report_path), "recommendation": report["recommendation"]}, ensure_ascii=False, indent=2))
    return 0


def benchmark_voice(
    voice_id: str,
    run_dir: Path,
    *,
    download_missing: bool,
    length_scale: float,
    sentence_silence: float,
    volume: float,
) -> dict[str, Any]:
    model_path, config_path = voice_paths(voice_id)
    if download_missing:
        download_voice(voice_id, model_path, config_path)
    if not model_path.exists() or not config_path.exists():
        return {
            "voice": voice_id,
            "provider": "piper",
            "status": "missing",
            "model": str(model_path),
            "config": str(config_path),
            "reason": "model/config missing; rerun with --download-missing on the target system",
        }

    voice_dir = run_dir / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for index, text in enumerate(TEST_TEXTS, start=1):
        raw_path = voice_dir / f"{index:02d}-native.wav"
        phone_path = voice_dir / f"{index:02d}-asterisk-8k.wav"
        config = TTSConfig(
            voice=voice_id,
            fallback_voice="de_DE-thorsten-medium",
            length_scale=length_scale,
            sentence_silence=sentence_silence,
            volume=volume,
        )
        start = time.perf_counter()
        _run_piper(text, raw_path, config)
        synth_seconds = time.perf_counter() - start
        start_convert = time.perf_counter()
        convert_for_asterisk(raw_path, phone_path, 8000)
        convert_seconds = time.perf_counter() - start_convert
        samples.append(
            {
                "index": index,
                "text": text,
                "native_wav": str(raw_path),
                "asterisk_wav": str(phone_path),
                "generation_seconds": round(synth_seconds, 3),
                "conversion_seconds": round(convert_seconds, 3),
                "native": audio_metrics(raw_path),
                "asterisk": audio_metrics(phone_path),
                "subjective_rating": "manual_listening_required",
            }
        )

    return {
        "voice": voice_id,
        "provider": "piper",
        "status": "ok",
        "model": str(model_path),
        "config": str(config_path),
        "language": "Deutsch",
        "locale": "de_DE",
        "length_scale": length_scale,
        "sentence_silence": sentence_silence,
        "volume": volume,
        "samples": samples,
        "avg_generation_seconds": avg_generation_seconds(samples),
        "total_asterisk_audio_seconds": round(sum(sample["asterisk"].get("duration_seconds", 0) for sample in samples), 3),
        "technical_score": technical_score(samples),
        "notes": voice_notes(voice_id),
    }


def voice_paths(voice_id: str) -> tuple[Path, Path]:
    return (
        get_settings().app_base_dir / "models" / "piper" / f"{voice_id}.onnx",
        get_settings().app_base_dir / "models" / "piper" / f"{voice_id}.onnx.json",
    )


def download_voice(voice_id: str, model_path: Path, config_path: Path) -> None:
    speaker, quality = piper_voice_parts(voice_id)
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/{speaker}/{quality}"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if not model_path.exists():
        urllib.request.urlretrieve(f"{base}/{voice_id}.onnx", model_path)
    if not config_path.exists():
        urllib.request.urlretrieve(f"{base}/{voice_id}.onnx.json", config_path)


def piper_voice_parts(voice_id: str) -> tuple[str, str]:
    prefix = "de_DE-"
    if not voice_id.startswith(prefix):
        raise ValueError(f"unsupported voice id: {voice_id}")
    rest = voice_id[len(prefix) :]
    speaker, quality = rest.rsplit("-", 1)
    return speaker, quality


def audio_metrics(path: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return metrics
    metrics["file_size"] = path.stat().st_size
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            metrics.update(
                {
                    "sample_rate": wav.getframerate(),
                    "channels": wav.getnchannels(),
                    "sample_width": wav.getsampwidth(),
                    "duration_seconds": round(wav.getnframes() / float(wav.getframerate()), 3),
                }
            )
            metrics.update(pcm_metrics(frames, wav.getsampwidth()))
    except Exception as exc:
        metrics["error"] = str(exc)
    metrics["quality_flags"] = quality_flags(metrics)
    return metrics


def pcm_metrics(frames: bytes, sample_width: int) -> dict[str, Any]:
    if sample_width != 2 or not frames:
        return {}
    samples = array("h")
    samples.frombytes(frames)
    if not samples:
        return {}
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    clipped = sum(1 for sample in samples if abs(sample) >= 32760)
    return {
        "peak_dbfs": dbfs(peak),
        "rms_dbfs": dbfs(rms),
        "clipping_percent": round((clipped / len(samples)) * 100, 4),
    }


def dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20 * math.log10(value / 32768.0), 3)


def quality_flags(metrics: dict[str, Any]) -> list[str]:
    flags = []
    if metrics.get("channels") != 1:
        flags.append("not_mono")
    if metrics.get("sample_rate") not in {8000, 16000, 22050, 24000, 44100, 48000}:
        flags.append("unexpected_sample_rate")
    if metrics.get("rms_dbfs") is None:
        flags.append("digital_silence")
    elif metrics["rms_dbfs"] < -32:
        flags.append("too_quiet")
    elif metrics["rms_dbfs"] > -10:
        flags.append("too_loud")
    if metrics.get("clipping_percent", 0) > 0.05:
        flags.append("possible_clipping")
    return flags


def technical_score(samples: list[dict[str, Any]]) -> float:
    scores = []
    for sample in samples:
        score = 100.0
        flags = sample["asterisk"].get("quality_flags", [])
        score -= len(flags) * 4
        score -= max(0.0, sample["generation_seconds"] - 1.5) * 2
        scores.append(max(0.0, score))
    return round(sum(scores) / max(1, len(scores)), 2)


def recommend_voice(voices: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok = [voice for voice in voices if voice.get("status") == "ok"]
    if not ok:
        return None
    best = sorted(
        ok,
        key=lambda item: (
            -item.get("technical_score", 0),
            item.get("avg_generation_seconds", 999),
            item.get("total_asterisk_audio_seconds", 999),
            item["voice"],
        ),
    )[0]
    return {
        "voice": best["voice"],
        "basis": "technical_metrics_only_manual_listening_required_before_default",
        "technical_score": best["technical_score"],
        "avg_generation_seconds": best.get("avg_generation_seconds"),
    }


def voice_notes(voice_id: str) -> str:
    voice = next((item for item in available_tts_voices() if item.voice_id == voice_id), None)
    return voice.description if voice else ""


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# TTS Voice Comparison",
        "",
        f"Created: {report['created_at']}",
        "",
        "| Voice | Status | Technical Score | Avg Generation | Total 8 kHz Audio | Notes |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for voice in report["voices"]:
        lines.append(
            f"| {voice['voice']} | {voice['status']} | {voice.get('technical_score', '')} | {voice.get('avg_generation_seconds', 0):.3f}s | {voice.get('total_asterisk_audio_seconds', 0):.2f}s | {voice.get('notes', voice.get('reason', ''))} |"
        )
    lines.extend(
        [
            "",
            "Subjective naturalness must be judged by listening to the `*-asterisk-8k.wav` files over the phone path before changing the production default.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def avg_generation_seconds(samples: list[dict[str, Any]]) -> float:
    return round(sum(sample["generation_seconds"] for sample in samples) / max(1, len(samples)), 3)


if __name__ == "__main__":
    raise SystemExit(main())
