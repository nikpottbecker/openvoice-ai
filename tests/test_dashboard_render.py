from fastapi.testclient import TestClient
import json


def test_dashboard_shell_renders_core_pages(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHBOARD_REQUIRE_ACCESS", "false")
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))

    from phone_agent.config import get_settings
    from phone_agent.dashboard.app import app

    get_settings.cache_clear()
    client = TestClient(app)

    for path in ("/", "/live", "/history", "/tasks", "/menu", "/tts", "/email", "/ai", "/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "OpenVoice AI" in response.text
        assert "command-palette" in response.text
        assert "Cloudflare Access" in response.text


def test_dashboard_settings_save_runtime_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHBOARD_REQUIRE_ACCESS", "false")
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))

    from phone_agent.config import get_settings, load_runtime_settings
    from phone_agent.dashboard.app import app

    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post(
        "/settings",
        data={
            "whisper_model": "small",
            "record_seconds": "8",
            "silence_seconds": "1.3",
            "min_record_seconds": "1.1",
            "post_playback_wait_seconds": "0.3",
            "max_turns": "7",
            "max_llm_rounds_per_call": "6",
            "llm_provider": "openrouter",
            "nvidia_model": "meta/llama-3.2-3b-instruct",
            "openrouter_model": "google/gemini-2.0-flash-lite-001",
            "openrouter_fallback_model": "openrouter/free",
            "openrouter_max_tokens": "70",
            "openrouter_temperature": "0.2",
            "openrouter_top_p": "0.7",
        },
    )

    assert response.status_code == 200
    saved = load_runtime_settings(get_settings())
    assert saved["whisper_model"] == "small"
    assert saved["record_seconds"] == 8
    assert "api_key" not in "\n".join(saved)


def test_dashboard_filters_non_real_call_fixtures(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHBOARD_REQUIRE_ACCESS", "false")
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))

    from phone_agent.config import get_settings
    from phone_agent.dashboard.app import app

    get_settings.cache_clear()
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir(parents=True)
    payload = {
        "started_at": "2026-07-20T21:30:00",
        "caller_id": "+491234",
        "transcript": [{"role": "user", "content": "Ich brauche einen Termin."}],
        "summary": "Terminwunsch",
        "ended": True,
    }
    for call_id in ("sim-1", "test-date-time", "demo-call", "sample-call"):
        (transcripts / f"{call_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    (transcripts / "live-call-1.json").write_text(json.dumps(payload), encoding="utf-8")

    client = TestClient(app)
    response = client.get("/api/calls")

    assert response.status_code == 200
    call_ids = [call["call_id"] for call in response.json()["calls"]]
    assert call_ids == ["live-call-1"]


def test_dashboard_status_api_uses_real_collectors(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHBOARD_REQUIRE_ACCESS", "false")
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))

    from phone_agent.config import get_settings
    from phone_agent.dashboard.app import app

    get_settings.cache_clear()
    client = TestClient(app)
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert "cpu_percent" in data["system"]
    assert "sip_registration" in data["asterisk"]
    assert "live_status" in data["overview"]
