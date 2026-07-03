import subprocess
import wave
import hashlib
from pathlib import Path

from .config import get_settings


def synthesize(text: str, output_wav: Path) -> Path:
    settings = get_settings()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = settings.app_base_dir / "cache" / "tts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_source = f"{settings.piper_model.name}\n{text.strip()}"
    key = hashlib.sha256(cache_source.encode("utf-8")).hexdigest()[:24]
    cached = cache_dir / f"{key}.wav"
    if cached.exists():
        output_wav.write_bytes(cached.read_bytes())
        return output_wav
    raw_wav = output_wav.with_suffix(".piper.wav")
    command = [
        str(settings.piper_bin),
        "--model",
        str(settings.piper_model),
        "--config",
        str(settings.piper_config),
        "--output_file",
        str(raw_wav),
    ]
    subprocess.run(
        command,
        input=text,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_wav),
            "-ar",
            "8000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    raw_wav.unlink(missing_ok=True)
    cached.write_bytes(output_wav.read_bytes())
    return output_wav


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return frames / float(rate)
