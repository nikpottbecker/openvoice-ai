#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


TIMING_RE = re.compile(
    r"timing call_id=(?P<call_id>\S+)(?: turn=(?P<turn>\d+))? phase=(?P<phase>\S+) "
    r"(?:seconds=(?P<seconds>[0-9.]+))?(?P<rest>.*)$"
)
TRANSCRIPT_RE = re.compile(r"transcript_full call_id=(?P<call_id>\S+) turn=(?P<turn>\d+) text=(?P<text>.*)$")
REPLY_RE = re.compile(
    r"conversation_state_(?:direct|slot|post_llm) call_id=(?P<call_id>\S+) .*?assistant_reply=(?P<reply>.*?) rolling_summary="
)
DTMF_RE = re.compile(
    r"dtmf_detected call_id=(?P<call_id>\S+) turn=(?P<turn>\d+) digit=(?P<digit>\S+) source=(?P<source>\S+)"
)
AUDIO_QUALITY_RE = re.compile(
    r"audio_quality call_id=(?P<call_id>\S+) turn=(?P<turn>\d+) path=(?P<path>\S+) (?P<rest>.*)$"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="/opt/phone-agent/logs/phone-agent.log")
    parser.add_argument("--call-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    calls = parse_log(Path(args.log))
    if args.call_id:
        calls = {args.call_id: calls.get(args.call_id, empty_call(args.call_id))}

    report = {"calls": [build_summary(call_id, data) for call_id, data in sorted(calls.items())]}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0


def empty_call(call_id: str) -> dict[str, Any]:
    return {"turns": defaultdict(dict), "transcripts": {}, "replies": [], "dtmf": []}


def parse_log(path: Path) -> dict[str, dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"turns": defaultdict(dict), "transcripts": {}, "replies": [], "dtmf": []}
    )
    if not path.exists():
        return {}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        message = line.split(" INFO ", 1)[-1].split(" WARNING ", 1)[-1].split(" ERROR ", 1)[-1]

        timing = TIMING_RE.search(message)
        if timing:
            call = calls[timing.group("call_id")]
            turn = int(timing.group("turn") or 0)
            phase = timing.group("phase")
            seconds = timing.group("seconds")
            if seconds is not None:
                call["turns"][turn][phase] = float(seconds)
            parse_extra_timing(call["turns"][turn], timing.group("rest"))
            continue

        transcript = TRANSCRIPT_RE.search(message)
        if transcript:
            calls[transcript.group("call_id")]["transcripts"][int(transcript.group("turn"))] = transcript.group("text")
            continue

        reply = REPLY_RE.search(message)
        if reply:
            calls[reply.group("call_id")]["replies"].append(reply.group("reply"))
            continue

        dtmf = DTMF_RE.search(message)
        if dtmf:
            calls[dtmf.group("call_id")]["dtmf"].append(
                {
                    "turn": int(dtmf.group("turn")),
                    "digit": dtmf.group("digit"),
                    "source": dtmf.group("source"),
                }
            )
            continue

        audio_quality = AUDIO_QUALITY_RE.search(message)
        if audio_quality:
            call = calls[audio_quality.group("call_id")]
            turn = int(audio_quality.group("turn"))
            call["turns"][turn]["audio_quality"] = parse_audio_quality(audio_quality.group("rest"))
            call["turns"][turn]["audio_quality"]["path"] = audio_quality.group("path")

    return calls


def parse_extra_timing(turn: dict[str, Any], rest: str) -> None:
    for key, value in re.findall(r"([a-z_]+)=([^\s]+)", rest):
        if key in {"recording_duration", "preprocessing", "whisper", "avg_logprob", "no_speech_prob", "compression_ratio"}:
            try:
                turn[key] = float(value)
            except ValueError:
                pass
        elif key in {"model", "retry_model", "segments"}:
            turn[key] = value


def parse_audio_quality(rest: str) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    for key, value in re.findall(r"([a-z_]+)=([^\s]+)", rest):
        if key in {"sample_rate", "channels"}:
            quality[key] = int(value) if value.isdigit() else value
        elif key in {"duration", "rms_dbfs", "peak_dbfs", "clipping_percent"}:
            try:
                quality[key] = float(value)
            except ValueError:
                quality[key] = None
        elif key == "flags":
            quality[key] = [] if value == "ok" else [item for item in value.split(",") if item]
    quality.setdefault("flags", [])
    return quality


def build_summary(call_id: str, data: dict[str, Any]) -> dict[str, Any]:
    turns = dict(sorted(data["turns"].items()))
    rows = []
    for turn, phases in turns.items():
        total_after_record = sum(phases.get(key, 0.0) for key in ("stt", "llm", "tts", "playback", "post_playback_wait"))
        rows.append(
            {
                "turn": turn,
                "record": phases.get("record"),
                "recording_audio": phases.get("recording_audio") or phases.get("recording_duration"),
                "stt": phases.get("stt"),
                "preprocessing": phases.get("preprocessing"),
                "whisper": phases.get("whisper"),
                "llm": phases.get("llm"),
                "tts": phases.get("tts"),
                "playback": phases.get("playback"),
                "dtmf_wait": phases.get("dtmf_wait"),
                "post_playback_wait": phases.get("post_playback_wait"),
                "after_record_total": round(total_after_record, 3),
                "avg_logprob": phases.get("avg_logprob"),
                "no_speech_prob": phases.get("no_speech_prob"),
                "audio_quality": phases.get("audio_quality", {}),
                "transcript": data["transcripts"].get(turn, ""),
            }
        )

    audio_flags = sorted(
        {
            flag
            for row in rows
            for flag in row.get("audio_quality", {}).get("flags", [])
        }
    )
    diagnosis = diagnose_call(rows, audio_flags)
    return {
        "call_id": call_id,
        "turn_count": len([row for row in rows if row["turn"] > 0]),
        "avg_stt": average(row["stt"] for row in rows),
        "avg_tts": average(row["tts"] for row in rows),
        "avg_playback": average(row["playback"] for row in rows),
        "avg_dtmf_wait": average(row["dtmf_wait"] for row in rows),
        "avg_after_record_total": average(row["after_record_total"] for row in rows if row["turn"] > 0),
        "max_after_record_total": max((row["after_record_total"] for row in rows if row["turn"] > 0), default=None),
        "dtmf_count": len(data.get("dtmf", [])),
        "dtmf_events": data.get("dtmf", []),
        "audio_quality_flags": audio_flags,
        "diagnosis": diagnosis,
        "reply_count": len(data["replies"]),
        "long_replies": [reply for reply in data["replies"] if len(reply) > 90],
        "turns": rows,
    }


def average(values: Any) -> float | None:
    clean = [value for value in values if isinstance(value, int | float)]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 3)


def print_human(report: dict[str, Any]) -> None:
    for call in report["calls"]:
        print(f"call_id={call['call_id']}")
        print(
            "avg_stt={avg_stt} avg_tts={avg_tts} avg_playback={avg_playback} "
            "avg_dtmf_wait={avg_dtmf_wait} avg_after_record_total={avg_after_record_total} "
            "max_after_record_total={max_after_record_total} dtmf_count={dtmf_count}".format(**call)
        )
        if call["long_replies"]:
            print("long_replies:")
            for reply in call["long_replies"]:
                print(f"  - {reply}")
        if call["diagnosis"]:
            print("diagnosis:")
            for item in call["diagnosis"]:
                print(f"  - {item}")
        for row in call["turns"]:
            if row["turn"] == 0:
                continue
            print(
                "turn={turn} record={record} audio={recording_audio} stt={stt} "
                "llm={llm} tts={tts} playback={playback} dtmf_wait={dtmf_wait} total={after_record_total} "
                "audio_flags={audio_flags} text={transcript}".format(
                    **row,
                    audio_flags=",".join(row.get("audio_quality", {}).get("flags", [])) or "ok",
                )
            )
        print()


def diagnose_call(rows: list[dict[str, Any]], audio_flags: list[str]) -> list[str]:
    diagnosis: list[str] = []
    if "digital_silence" in audio_flags:
        diagnosis.append("recording_contains_digital_silence_check_record_timing_or_rtp")
    if "very_short_audio" in audio_flags:
        diagnosis.append("recording_too_short_check_min_record_or_barge_in")
    if "very_low_level" in audio_flags:
        diagnosis.append("recording_too_quiet_check_gain_or_normalization")
    if "very_hot_level" in audio_flags or "possible_clipping" in audio_flags:
        diagnosis.append("recording_too_hot_or_clipping_reduce_gain")
    if "unexpected_sample_rate" in audio_flags or "not_mono" in audio_flags:
        diagnosis.append("unexpected_audio_format_check_asterisk_recording_pipeline")
    empty_transcripts = [row for row in rows if row.get("stt") is not None and not row.get("transcript")]
    if empty_transcripts and not audio_flags:
        diagnosis.append("empty_transcript_without_audio_flag_check_whisper_model_or_prompt")
    slow_turns = [row for row in rows if (row.get("after_record_total") or 0) > 5.0]
    if slow_turns:
        diagnosis.append("response_latency_above_5s_check_stt_llm_tts_breakdown")
    return diagnosis


if __name__ == "__main__":
    raise SystemExit(main())
