import json

from phone_agent.config import get_settings, load_runtime_settings, save_runtime_settings


def test_runtime_settings_override_safe_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    save_runtime_settings({"whisper_model": "small", "record_seconds": 9, "openrouter_api_key": "secret"})
    get_settings.cache_clear()

    settings = get_settings()
    saved = load_runtime_settings(settings)

    assert settings.whisper_model == "small"
    assert settings.record_seconds == 9
    assert "openrouter_api_key" not in saved


def test_runtime_settings_ignore_unknown_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()
    path = tmp_path / "config" / "runtime_settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"smtp_password": "secret", "silence_seconds": 1.2}), encoding="utf-8")

    assert load_runtime_settings(get_settings()) == {"silence_seconds": 1.2}
