import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import get_settings


@dataclass(frozen=True)
class TTSVoice:
    voice_id: str
    provider: str
    language: str
    locale: str
    quality: str
    gender: str
    description: str
    model_url: str = ""
    config_url: str = ""


@dataclass(frozen=True)
class TTSConfig:
    provider: str = "piper"
    voice: str = "de_DE-thorsten-medium"
    fallback_voice: str = "de_DE-thorsten-medium"
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w_scale: float = 0.8
    sentence_silence: float = 0.22
    volume: float = 1.0
    output_sample_rate: int = 8000

    def model_path(self) -> Path:
        settings = get_settings()
        if self.voice == settings.piper_model.stem and settings.piper_model.exists():
            return settings.piper_model
        return settings.app_base_dir / "models" / "piper" / f"{self.voice}.onnx"

    def config_path(self) -> Path:
        settings = get_settings()
        if self.voice == settings.piper_model.stem and settings.piper_config.exists():
            return settings.piper_config
        return settings.app_base_dir / "models" / "piper" / f"{self.voice}.onnx.json"

    def fallback_model_path(self) -> Path:
        return get_settings().app_base_dir / "models" / "piper" / f"{self.fallback_voice}.onnx"

    def fallback_config_path(self) -> Path:
        return get_settings().app_base_dir / "models" / "piper" / f"{self.fallback_voice}.onnx.json"


def tts_config_path() -> Path:
    return get_settings().config_dir / "tts_settings.json"


def load_tts_config(path: Path | None = None) -> TTSConfig:
    settings = get_settings()
    env_config = TTSConfig(
        provider=getattr(settings, "tts_provider", "piper"),
        voice=getattr(settings, "tts_voice", settings.piper_model.stem),
        fallback_voice=getattr(settings, "tts_fallback_voice", settings.piper_model.stem),
        length_scale=getattr(settings, "tts_length_scale", 1.0),
        noise_scale=getattr(settings, "tts_noise_scale", 0.667),
        noise_w_scale=getattr(settings, "tts_noise_w_scale", 0.8),
        sentence_silence=getattr(settings, "tts_sentence_silence", 0.22),
        volume=getattr(settings, "tts_volume", 1.0),
        output_sample_rate=getattr(settings, "tts_output_sample_rate", 8000),
    )
    config_path = path or tts_config_path()
    if not config_path.exists():
        return env_config
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return validate_tts_config({**asdict(env_config), **data})


def save_tts_config(config: TTSConfig, path: Path | None = None) -> None:
    config_path = path or tts_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


def validate_tts_config(data: dict[str, Any]) -> TTSConfig:
    provider = str(data.get("provider", "piper"))
    if provider != "piper":
        raise ValueError("only provider 'piper' is currently supported locally")
    voice = _clean_voice_id(data.get("voice", "de_DE-thorsten-medium"))
    fallback_voice = _clean_voice_id(data.get("fallback_voice", voice))
    return TTSConfig(
        provider=provider,
        voice=voice,
        fallback_voice=fallback_voice,
        length_scale=_bounded_float(data.get("length_scale", 1.0), 0.75, 1.45, "length_scale"),
        noise_scale=_bounded_float(data.get("noise_scale", 0.667), 0.1, 1.2, "noise_scale"),
        noise_w_scale=_bounded_float(data.get("noise_w_scale", 0.8), 0.1, 1.4, "noise_w_scale"),
        sentence_silence=_bounded_float(data.get("sentence_silence", 0.22), 0.0, 1.5, "sentence_silence"),
        volume=_bounded_float(data.get("volume", 1.0), 0.4, 1.8, "volume"),
        output_sample_rate=int(data.get("output_sample_rate", 8000)),
    )


def available_tts_voices() -> list[TTSVoice]:
    return [
        TTSVoice("de_DE-thorsten-medium", "piper", "Deutsch", "de_DE", "medium", "male", "Aktuelle Fallback-Stimme; robust, aber oft weniger natürlich."),
        TTSVoice("de_DE-thorsten-high", "piper", "Deutsch", "de_DE", "high", "male", "Höhere Qualität derselben Stimme; besser für Vergleichsproben."),
        TTSVoice("de_DE-thorsten_emotional-medium", "piper", "Deutsch", "de_DE", "medium", "male", "Ausdrucksstärker, muss auf Telefon-Natürlichkeit geprüft werden."),
        TTSVoice("de_DE-mls-medium", "piper", "Deutsch", "de_DE", "medium", "mixed", "MLS Mehrsprecher-Modell; Kandidat für neutralere Aussprache."),
        TTSVoice("de_DE-karlsson-low", "piper", "Deutsch", "de_DE", "low", "male", "Leichtgewichtig; nur behalten, wenn Telefonverständlichkeit überzeugt."),
        TTSVoice("de_DE-kerstin-low", "piper", "Deutsch", "de_DE", "low", "female", "Leichtgewichtig; möglicher natürlicherer weiblicher Kandidat."),
        TTSVoice("de_DE-eva_k-x_low", "piper", "Deutsch", "de_DE", "x_low", "female", "Sehr klein; voraussichtlich schnell, aber Qualitätsrisiko."),
        TTSVoice("de_DE-pavoque-low", "piper", "Deutsch", "de_DE", "low", "male", "Alternative leichte deutsche Stimme."),
        TTSVoice("de_DE-ramona-low", "piper", "Deutsch", "de_DE", "low", "female", "Alternative leichte deutsche Stimme."),
    ]


def voice_by_id(voice_id: str) -> TTSVoice | None:
    return next((voice for voice in available_tts_voices() if voice.voice_id == voice_id), None)


def _clean_voice_id(value: Any) -> str:
    voice_id = str(value or "").strip()
    if not voice_id:
        raise ValueError("voice must not be empty")
    allowed = {voice.voice_id for voice in available_tts_voices()}
    if voice_id not in allowed:
        raise ValueError(f"unsupported voice: {voice_id}")
    return voice_id


def _bounded_float(value: Any, minimum: float, maximum: float, name: str) -> float:
    number = float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number
