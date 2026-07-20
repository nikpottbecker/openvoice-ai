import hashlib
import logging
import subprocess
import wave
import audioop
from pathlib import Path

from .config import get_settings
from .tts_config import TTSConfig, load_tts_config

logger = logging.getLogger(__name__)


def synthesize(text: str, output_wav: Path) -> Path:
    config = load_tts_config()
    try:
        return synthesize_with_config(text, output_wav, config)
    except Exception:
        if config.fallback_voice == config.voice:
            raise
        logger.exception("tts_primary_failed voice=%s fallback=%s", config.voice, config.fallback_voice)
        fallback = TTSConfig(
            provider=config.provider,
            voice=config.fallback_voice,
            fallback_voice=config.fallback_voice,
            length_scale=config.length_scale,
            noise_scale=config.noise_scale,
            noise_w_scale=config.noise_w_scale,
            sentence_silence=config.sentence_silence,
            volume=config.volume,
            output_sample_rate=config.output_sample_rate,
        )
        return synthesize_with_config(text, output_wav, fallback)


def synthesize_with_config(text: str, output_wav: Path, config: TTSConfig) -> Path:
    settings = get_settings()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = settings.app_base_dir / "cache" / "tts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_source = "\n".join(
        [
            config.provider,
            config.voice,
            str(config.length_scale),
            str(config.noise_scale),
            str(config.noise_w_scale),
            str(config.sentence_silence),
            str(config.volume),
            str(config.output_sample_rate),
            text.strip(),
        ]
    )
    key = hashlib.sha256(cache_source.encode("utf-8")).hexdigest()[:24]
    cached = cache_dir / f"{key}.wav"
    if cached.exists():
        output_wav.write_bytes(cached.read_bytes())
        return output_wav

    raw_wav = output_wav.with_suffix(".piper.wav")
    _run_piper(text, raw_wav, config)
    convert_for_asterisk(raw_wav, output_wav, config.output_sample_rate)
    raw_wav.unlink(missing_ok=True)
    cached.write_bytes(output_wav.read_bytes())
    return output_wav


def _run_piper(text: str, raw_wav: Path, config: TTSConfig) -> None:
    settings = get_settings()
    model_path = config.model_path()
    config_path = config.config_path()
    command = [
        str(settings.piper_bin),
        "--model",
        str(model_path),
        "--config",
        str(config_path),
        "--output_file",
        str(raw_wav),
        "--length-scale",
        str(config.length_scale),
        "--noise-scale",
        str(config.noise_scale),
        "--noise-w-scale",
        str(config.noise_w_scale),
        "--sentence-silence",
        str(config.sentence_silence),
        "--volume",
        str(config.volume),
    ]
    data_dir = settings.piper_bin.parent / "espeak-ng-data"
    if data_dir.exists():
        command.extend(["--data-dir", str(data_dir)])
    subprocess.run(
        command,
        input=text,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def convert_for_asterisk(source_wav: Path, output_wav: Path, sample_rate: int = 8000) -> None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source_wav),
                "-af",
                "aresample=resampler=soxr:precision=28,loudnorm=I=-18:LRA=7:TP=-2.0",
                "-ar",
                str(sample_rate),
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
    except FileNotFoundError:
        _convert_pcm_wav_python(source_wav, output_wav, sample_rate)


def _convert_pcm_wav_python(source_wav: Path, output_wav: Path, sample_rate: int) -> None:
    with wave.open(str(source_wav), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if width != 2:
        raise ValueError("Python fallback supports 16-bit PCM WAV only")
    if channels == 2:
        frames = audioop.tomono(frames, width, 0.5, 0.5)
    elif channels != 1:
        raise ValueError(f"Python fallback supports mono/stereo WAV only, got {channels} channels")
    converted, _state = audioop.ratecv(frames, width, 1, rate, sample_rate, None)
    with wave.open(str(output_wav), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(converted)


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return frames / float(rate)
