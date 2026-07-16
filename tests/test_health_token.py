"""Tests for the IDE-token reveal/overwrite and token-health endpoints."""
import pytest
from fastapi.testclient import TestClient


def _reload_app(tmp_path, monkeypatch):
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    for _key in ("API_KEY", "DASHBOARD_PASSWORD", "TRAE_IDE_TOKEN"):
        monkeypatch.setenv(_key, "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    import importlib
    import config, session_auth, deps, routes_openai, routes_dashboard, main
    importlib.reload(config)
    config.API_KEY = ""
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(deps)
    importlib.reload(routes_openai)
    importlib.reload(routes_dashboard)
    importlib.reload(main)
    return config


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Unauthenticated TestClient (no lifespan, so no health loop)."""
    _reload_app(tmp_path, monkeypatch)
    from main import app
    return TestClient(app)


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    """TestClient with API_KEY set to 'testkey'."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "testkey")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("TRAE_IDE_TOKEN", "")
    import importlib
    import config, session_auth, deps, routes_openai, routes_dashboard, main
    importlib.reload(config)
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(deps)
    importlib.reload(routes_openai)
    importlib.reload(routes_dashboard)
    importlib.reload(main)
    from main import app
    return TestClient(app)


# ── IDE token ────────────────────────────────────────────────────────────────

def test_ide_token_get_empty_when_unset(client):
    resp = client.get("/config/ide-token")
    assert resp.status_code == 200
    assert resp.json() == {"token": ""}


def test_ide_token_put_sets_and_reveals(client):
    assert client.put("/config/ide-token", json={"token": "  jwt-abc  "}).status_code == 200
    # Whitespace is trimmed; the real value is returned for the reveal toggle.
    assert client.get("/config/ide-token").json() == {"token": "jwt-abc"}
    # /config still masks it.
    assert client.get("/config").json()["TRAE_IDE_TOKEN"] == "••••••"


def test_ide_token_put_empty_clears(client):
    client.put("/config/ide-token", json={"token": "jwt-abc"})
    assert client.put("/config/ide-token", json={"token": ""}).json() == {"ok": True, "set": False}
    assert client.get("/config/ide-token").json() == {"token": ""}
    assert client.get("/config").json()["TRAE_IDE_TOKEN"] == "(not set)"


def test_ide_token_put_mutates_running_headers(client, tmp_path, monkeypatch):
    import config
    client.put("/config/ide-token", json={"token": "jwt-xyz"})
    assert config.get_ide_token() == "jwt-xyz"
    assert config.TRAE_HEADERS["x-ide-token"] == "jwt-xyz"
    assert config.TRAE_HEADERS["authorization"] == "Cloud-IDE-JWT jwt-xyz"


def test_ide_token_endpoints_require_auth(authed_client):
    assert authed_client.get("/config/ide-token").status_code == 401
    assert authed_client.put("/config/ide-token", json={"token": "x"}).status_code == 401


# ── Token health ─────────────────────────────────────────────────────────────

def test_trae_health_status_shape(client):
    data = client.get("/trae-health").json()
    for key in ("status", "checked_at", "next_check_at", "detail", "model_count", "interval_hours"):
        assert key in data


def test_trae_health_check_runs(client):
    # list_models is stubbed by conftest to return [] → healthy, 0 models.
    data = client.post("/trae-health/check").json()
    assert data["status"] == "ok"
    assert data["model_count"] == 0


def test_trae_health_interval_updates(client):
    data = client.put("/trae-health/interval", json={"hours": 6}).json()
    assert data["interval_hours"] == 6


def test_trae_health_interval_rejects_out_of_range(client):
    assert client.put("/trae-health/interval", json={"hours": 0}).status_code == 400
    assert client.put("/trae-health/interval", json={"hours": 1000}).status_code == 400


def test_trae_health_requires_auth(authed_client):
    assert authed_client.get("/trae-health").status_code == 401
    assert authed_client.post("/trae-health/check").status_code == 401
