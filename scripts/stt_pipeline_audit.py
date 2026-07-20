#!/usr/bin/env python3
"""Benchmark the STT pipeline on real call recordings without changing runtime behavior."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil
from faster_whisper import WhisperModel

try:
    from phone_agent.stt import _resolve_local_model
except Exception:
    _resolve_local_model = lambda model_name: model_name


@dataclass(frozen=True)
class PrepVariant:
    name: str
    ffmpeg_filter: str


@dataclass(frozen=True)
class WhisperVariant:
    model: str
    beam_size: int
    temperature: float = 0.0
    vad_filter: bool = False
    initial_prompt: str = ""


PREP_VARIANTS = (
    PrepVariant("current", "highpass=f=80,lowpass=f=3800,loudnorm=I=-18:LRA=8:TP=-2.0,volume=1.2"),
    PrepVariant("normalize_only", "loudnorm=I=-18:LRA=8:TP=-2.0"),
    PrepVariant("telephone_band_soft", "highpass=f=70,lowpass=f=3900,loudnorm=I=-18:LRA=8:TP=-2.0"),
    PrepVariant("telephone_agc_soft", "highpass=f=70,lowpass=f=3900,dynaudnorm=f=150:g=9:p=0.75,loudnorm=I=-18:LRA=8:TP=-2.0"),
    PrepVariant("no_loudnorm", "highpass=f=70,lowpass=f=3900,volume=2.0"),
)

WHISPER_VARIANTS = (
    WhisperVariant("base", 1),
    WhisperVariant("base", 3),
    WhisperVariant("base", 5, initial_prompt="Telefonat auf Deutsch. Es geht oft um Termine, Namen, Uhrzeiten, Fotoshooting, Rueckruf oder Anfragen."),
    WhisperVariant("small", 1),
    WhisperVariant("small", 3),
    WhisperVariant("small", 5, initial_prompt="Telefonat auf Deutsch. Es geht oft um Termine, Namen, Uhrzeiten, Fotoshooting, Rueckruf oder Anfragen."),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default="/opt/phone-agent")
    parser.add_argument("--call-id", action="append", default=[])
    parser.add_argument("--limit-turns", type=int, default=0)
    parser.add_argument("--include-medium", action="store_true")
    parser.add_argument("--include-large", action="store_true")
    parser.add_argument("--reference-json", default="")
    parser.add_argument("--write-reference-template", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    call_ids = args.call_id or latest_call_ids(app_dir, limit=2)
    if args.write_reference_template:
        write_reference_template(app_dir, call_ids, Path(args.write_reference_template), args.limit_turns)
        return 0

    whisper_variants = list(WHISPER_VARIANTS)
    if args.include_medium:
        whisper_variants.append(WhisperVariant("medium", 1))
    if args.include_large:
        whisper_variants.extend(
            [
                WhisperVariant("large-v3", 1),
                WhisperVariant("large-v3-turbo", 1),
            ]
        )
    references = load_references(args.reference_json)

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
        output["calls"].append(audit_call(app_dir, call_id, wavs, whisper_variants, references))

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


def write_reference_template(app_dir: Path, call_ids: list[str], output: Path, limit_turns: int = 0) -> None:
    references: dict[str, str] = {}
    metadata: dict[str, Any] = {"calls": {}}
    for call_id in call_ids:
        wavs = real_call_wavs(app_dir, call_id)
        if limit_turns:
            wavs = wavs[:limit_turns]
        metadata["calls"][call_id] = []
        for wav in wavs:
            references[wav.name] = ""
            metadata["calls"][call_id].append(
                {
                    "wav": str(wav),
                    "file_size": wav.stat().st_size,
                    "audio": audio_metrics(wav),
                }
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_path = output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reference_template": str(output), "metadata": str(metadata_path)}, ensure_ascii=False))


def audit_call(
    app_dir: Path,
    call_id: str,
    wavs: list[Path],
    whisper_variants: list[WhisperVariant],
    references: dict[str, str],
) -> dict[str, Any]:
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
                reference = references.get(wav.name) or references.get(wav.stem) or ""
                prep_result["transcripts"].append(run_whisper(prepared, whisper, model_cache, reference))
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


def run_whisper(
    path: Path,
    variant: WhisperVariant,
    model_cache: dict[str, WhisperModel],
    reference: str,
) -> dict[str, Any]:
    model = model_cache.get(variant.model)
    load_seconds = 0.0
    if model is None:
        start_load = time.perf_counter()
        model = WhisperModel(_resolve_local_model(variant.model), device="cpu", compute_type="int8")
        model_cache[variant.model] = model
        load_seconds = time.perf_counter() - start_load

    start = time.perf_counter()
    segments, info = model.transcribe(
        str(path),
        language="de",
        task="transcribe",
        vad_filter=variant.vad_filter,
        condition_on_previous_text=False,
        beam_size=variant.beam_size,
        temperature=variant.temperature,
        initial_prompt=variant.initial_prompt or None,
    )
    runtime_seconds = time.perf_counter() - start
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    duration_seconds = audio_duration_seconds(path)
    result = {
        "model": variant.model,
        "beam_size": variant.beam_size,
        "temperature": variant.temperature,
        "vad_filter": variant.vad_filter,
        "initial_prompt": bool(variant.initial_prompt),
        "load_seconds": round(load_seconds, 3),
        "runtime_seconds": round(runtime_seconds, 3),
        "realtime_factor": round(runtime_seconds / duration_seconds, 3) if duration_seconds else None,
        "rss_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 1),
        "language_probability": round(getattr(info, "language_probability", 0.0) or 0.0, 3),
        "raw_transcript": text.strip(),
        "notes": transcript_notes(text),
    }
    if reference:
        result["reference"] = reference
        result["wer"] = word_error_rate(reference, text)
        result["cer"] = character_error_rate(reference, text)
        result["word_accuracy"] = round(max(0.0, 1.0 - result["wer"]) * 100.0, 2)
        result["char_accuracy"] = round(max(0.0, 1.0 - result["cer"]) * 100.0, 2)
    return result


def audio_metrics(path: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return metrics
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            metrics.update(
                {
                    "channels": wav.getnchannels(),
                    "sample_rate": wav.getframerate(),
                    "sample_width": wav.getsampwidth(),
                    "frames": wav.getnframes(),
                    "duration_seconds": round(wav.getnframes() / float(wav.getframerate()), 3),
                }
            )
            metrics.update(pcm_metrics(frames, wav.getsampwidth()))
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
    astats = run_ffmpeg_filter(path, "astats=metadata=1:reset=1")
    peak = re.findall(r"Peak level dB:\s*([-0-9.]+)", astats)
    rms = re.findall(r"RMS level dB:\s*([-0-9.]+)", astats)
    if peak:
        metrics["peak_level_db"] = float(peak[-1])
    if rms:
        metrics["rms_level_db"] = float(rms[-1])
    metrics["possible_clipping"] = metrics.get("max_volume_db", -99) >= -0.2
    metrics["quality_flags"] = audio_quality_flags(metrics)
    return metrics


def pcm_metrics(frames: bytes, sample_width: int) -> dict[str, Any]:
    if sample_width != 2 or not frames:
        return {}
    samples = array("h")
    samples.frombytes(frames)
    if not samples:
        return {}
    peak = max(abs(sample) for sample in samples)
    square_sum = sum(sample * sample for sample in samples)
    rms = math.sqrt(square_sum / len(samples))
    clipped = sum(1 for sample in samples if abs(sample) >= 32760)
    return {
        "pcm_peak_sample": peak,
        "pcm_peak_dbfs": dbfs(peak),
        "pcm_rms_dbfs": dbfs(rms),
        "pcm_clipping_percent": round((clipped / len(samples)) * 100.0, 4),
    }


def dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20 * math.log10(value / 32768.0), 3)


def audio_quality_flags(metrics: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if metrics.get("duration_seconds", 0) < 1.0:
        flags.append("very_short_audio")
    if metrics.get("sample_rate") not in {8000, 16000}:
        flags.append("unexpected_sample_rate")
    if metrics.get("channels") != 1:
        flags.append("not_mono")
    rms = metrics.get("pcm_rms_dbfs")
    if rms is None:
        flags.append("digital_silence")
    elif rms < -38:
        flags.append("very_low_level")
    elif rms > -10:
        flags.append("very_hot_level")
    if metrics.get("pcm_clipping_percent", 0.0) > 0.1 or metrics.get("possible_clipping"):
        flags.append("possible_clipping")
    return flags


def audio_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return 0.0


def run_ffmpeg_filter(path: Path, audio_filter: str) -> str:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", audio_filter, "-f", "null", "-"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc.stdout + proc.stderr
    except FileNotFoundError:
        return "ffmpeg_missing"


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
    rows: dict[tuple[str, str, int, bool], list[dict[str, Any]]] = {}
    for call in calls:
        for turn in call["turns"]:
            for variant in turn["variants"]:
                for transcript in variant["transcripts"]:
                    key = (
                        variant["prep"],
                        transcript["model"],
                        transcript["beam_size"],
                        transcript["initial_prompt"],
                    )
                    rows.setdefault(key, []).append(transcript)

    summary = []
    for (prep, model, beam, initial_prompt), transcripts in sorted(rows.items()):
        wer_values = [item["wer"] for item in transcripts if "wer" in item]
        cer_values = [item["cer"] for item in transcripts if "cer" in item]
        row = {
            "prep": prep,
            "model": model,
            "beam_size": beam,
            "initial_prompt": initial_prompt,
            "avg_runtime_seconds": round(
                sum(item["runtime_seconds"] for item in transcripts) / len(transcripts), 3
            ),
            "avg_realtime_factor": round(
                sum(item["realtime_factor"] or 0 for item in transcripts) / len(transcripts), 3
            ),
            "max_rss_mb": max(item.get("rss_mb", 0) for item in transcripts),
            "avg_word_accuracy": round(
                sum(max(0.0, 1.0 - value) * 100.0 for value in wer_values) / len(wer_values),
                2,
            )
            if wer_values
            else None,
            "avg_char_accuracy": round(
                sum(max(0.0, 1.0 - value) * 100.0 for value in cer_values) / len(cer_values),
                2,
            )
            if cer_values
            else None,
            "empty_transcripts": sum(1 for item in transcripts if not item["raw_transcript"]),
            "hallucination_flags": sum(
                1 for item in transcripts if "possible_hallucination" in item["notes"]
            ),
        }
        if wer_values:
            row["rank_basis"] = "reference_accuracy"
            row["quality_score"] = round(
                (row["avg_word_accuracy"] or 0) * 0.75
                + (row["avg_char_accuracy"] or 0) * 0.25
                - row["hallucination_flags"] * 5,
                3,
            )
        else:
            row["rank_basis"] = "diagnostic_only_no_reference"
            row["quality_score"] = round(
                100
                - row["empty_transcripts"] * 25
                - row["hallucination_flags"] * 10
                - row["avg_realtime_factor"],
                3,
            )
        summary.append(row)
    return sorted(
        summary,
        key=lambda row: (
            -(row["quality_score"] or 0),
            row["avg_runtime_seconds"],
            row["max_rss_mb"],
        ),
    )


def load_references(path: str) -> dict[str, str]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    raise SystemExit("reference-json must be an object: wav filename/stem -> reference transcript")


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_words(reference)
    hyp = normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return round(previous[-1] / len(ref), 4)


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_chars(reference)
    hyp = normalize_chars(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return round(previous[-1] / len(ref), 4)


def normalize_words(text: str) -> list[str]:
    if "\u00c3" in text or "\u00c2" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = text.lower()
    text = (
        text.replace("\u00e4", "ae")
        .replace("\u00f6", "oe")
        .replace("\u00fc", "ue")
        .replace("\u00df", "ss")
    )
    return re.findall(r"[a-z0-9]+", text)


def normalize_chars(text: str) -> str:
    return "".join(normalize_words(text))


def hardware_info() -> dict[str, Any]:
    return {
        "cpu_count": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
    }


if __name__ == "__main__":
    raise SystemExit(main())
