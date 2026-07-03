#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .agent import PhoneAgent
from .config import get_settings
from .logging_setup import configure_logging
from .stt import transcribe
from .tts import synthesize


logger = logging.getLogger(__name__)


def make_input_audio(text: str, path: Path) -> None:
    settings = get_settings()
    synthesize(text, path)
    # Normalize for the same path Asterisk recordings use.
    normalized = path.with_name(path.stem + "-8k.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ar", "16000", "-ac", "1", str(normalized)],
        check=True,
    )
    normalized.replace(path)


async def run_simulation(text: str, caller_id: str) -> dict:
    settings = get_settings()
    call_id = "sim-" + uuid.uuid4().hex[:12]
    agent = PhoneAgent(call_id=call_id, caller_id=caller_id)
    with tempfile.TemporaryDirectory() as tmpdir:
        input_audio = Path(tmpdir) / "caller.wav"
        timings = {}
        start = time.perf_counter()
        make_input_audio(text, input_audio)
        timings["recording_synthesis"] = round(time.perf_counter() - start, 3)
        start = time.perf_counter()
        transcript = transcribe(input_audio)
        timings["stt"] = round(time.perf_counter() - start, 3)
        start = time.perf_counter()
        result = await agent.handle_turn(transcript or text)
        timings["llm"] = round(time.perf_counter() - start, 3)
        reply_audio = settings.recordings_dir / f"{call_id}-reply.wav"
        start = time.perf_counter()
        synthesize(result.reply, reply_audio)
        timings["tts"] = round(time.perf_counter() - start, 3)
    return {
        "call_id": call_id,
        "caller_id": caller_id,
        "input_text": text,
        "stt_text": transcript,
        "intent": result.intent,
        "reply": result.reply,
        "summary": result.summary,
        "reply_audio": str(reply_audio),
        "state_file": str(settings.transcripts_dir / f"{call_id}.json"),
        "timings": timings,
    }


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--text",
        default="Hallo, ich bin Example Caller und moechte morgen um 14 Uhr einen Termin wegen einer Projektbesprechung vereinbaren.",
    )
    parser.add_argument("--caller-id", default="+490000000000")
    args = parser.parse_args()
    result = asyncio.run(run_simulation(args.text, args.caller_id))
    logger.info("simulation_finished call_id=%s intent=%s", result["call_id"], result["intent"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
