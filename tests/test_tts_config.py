import json

import pytest

from phone_agent.config import get_settings
from phone_agent.tts_config import TTSConfig, load_tts_config, save_tts_config, validate_tts_config


def test_tts_config_defaults_to_current_piper_voice(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    config = load_tts_config()

    assert config.provider == "piper"
    assert config.voice == "de_DE-thorsten-medium"
    assert config.fallback_voice == "de_DE-thorsten-medium"
    assert config.output_sample_rate == 8000


def test_tts_config_file_overrides_voice_without_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()
    config_path = tmp_path / "config" / "tts_settings.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"voice": "de_DE-thorsten-high", "fallback_voice": "de_DE-thorsten-medium", "volume": 0.9}),
        encoding="utf-8",
    )

    config = load_tts_config()

    assert config.voice == "de_DE-thorsten-high"
    assert config.fallback_voice == "de_DE-thorsten-medium"
    assert config.volume == 0.9


def test_validate_tts_config_rejects_unknown_voice() -> None:
    with pytest.raises(ValueError, match="unsupported voice"):
        validate_tts_config({"voice": "de_DE-made-up-medium"})


def test_save_tts_config_writes_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    save_tts_config(TTSConfig(voice="de_DE-kerstin-low", fallback_voice="de_DE-thorsten-medium"))

    data = json.loads((tmp_path / "config" / "tts_settings.json").read_text(encoding="utf-8"))
    assert data["voice"] == "de_DE-kerstin-low"
    assert data["fallback_voice"] == "de_DE-thorsten-medium"
