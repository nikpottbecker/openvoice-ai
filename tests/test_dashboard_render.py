from fastapi.testclient import TestClient


def test_dashboard_shell_renders_core_pages(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHBOARD_REQUIRE_ACCESS", "false")
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))

    from phone_agent.config import get_settings
    from phone_agent.dashboard.app import app

    get_settings.cache_clear()
    client = TestClient(app)

    for path in ("/", "/live", "/history", "/tasks", "/menu", "/email", "/ai", "/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "OpenVoice AI" in response.text
        assert "command-palette" in response.text
        assert "Cloudflare Access" in response.text
