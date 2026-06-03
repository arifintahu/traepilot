"""Tests for /config and /dashboard endpoints."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a fresh temp DB and no API key."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("API_KEY", raising=False)
    # Clear sensitive fields so masking tests see "(not set)"
    for _key in ("TRAE_IDE_TOKEN", "TRAE_MACHINE_ID", "TRAE_DEVICE_ID"):
        monkeypatch.delenv(_key, raising=False)
    # Re-import app after env change so lifespan sees the temp DB
    import importlib
    import main
    importlib.reload(main)
    from main import app
    return TestClient(app)


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    """TestClient with API_KEY set to 'testkey'."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "testkey")
    import importlib
    import config, main
    importlib.reload(config)   # re-reads API_KEY from env
    importlib.reload(main)     # picks up new config.API_KEY
    from main import app
    return TestClient(app)


# ── /config ──────────────────────────────────────────────────────────────────

def test_config_returns_200(client):
    resp = client.get("/config")
    assert resp.status_code == 200


def test_config_has_all_expected_keys(client):
    resp = client.get("/config")
    data = resp.json()
    expected = {
        "TRAE_BASE_URL", "BIND_HOST", "BIND_PORT", "API_KEY",
        "TRAE_EXCLUDE_MODELS", "TRAE_APP_ID", "TRAE_DEVICE_BRAND",
        "TRAE_DEVICE_CPU", "TRAE_DEVICE_ID", "TRAE_DEVICE_TYPE",
        "TRAE_IDE_TOKEN", "TRAE_IDE_VERSION", "TRAE_IDE_VERSION_CODE",
        "TRAE_MACHINE_ID", "TRAE_OS_VERSION", "TRAE_PLUGIN_CHANNEL",
    }
    assert expected.issubset(set(data.keys()))


def test_config_masks_sensitive_fields_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("TRAE_IDE_TOKEN", "secret-token")
    monkeypatch.setenv("TRAE_MACHINE_ID", "machine-abc")
    monkeypatch.setenv("TRAE_DEVICE_ID", "device-xyz")
    import importlib, config, main
    importlib.reload(config)
    importlib.reload(main)
    from main import app
    c = TestClient(app)
    data = c.get("/config").json()
    assert data["TRAE_IDE_TOKEN"] == "••••••"
    assert data["TRAE_MACHINE_ID"] == "••••••"
    assert data["TRAE_DEVICE_ID"] == "••••••"


def test_config_shows_not_set_for_empty_sensitive(client):
    resp = client.get("/config")
    data = resp.json()
    # With no env vars set, sensitive fields should show "(not set)"
    assert data["TRAE_IDE_TOKEN"] == "(not set)"


def test_config_requires_auth_when_api_key_configured(authed_client):
    resp = authed_client.get("/config")
    assert resp.status_code == 401


def test_config_accepts_valid_bearer_token(authed_client):
    resp = authed_client.get(
        "/config", headers={"Authorization": "Bearer testkey"}
    )
    assert resp.status_code == 200


# ── /dashboard ───────────────────────────────────────────────────────────────

def test_dashboard_returns_200(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_returns_html(client):
    resp = client.get("/dashboard")
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_contains_traepilot(client):
    resp = client.get("/dashboard")
    assert b"TraePilot" in resp.content
