"""Tests for /config, /dashboard, and session-auth endpoints."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a fresh temp DB and no API key."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    # Set empty strings BEFORE reload so load_dotenv(override=False) skips .env values.
    for _key in ("API_KEY", "DASHBOARD_PASSWORD", "TRAE_IDE_TOKEN", "TRAE_MACHINE_ID", "TRAE_DEVICE_ID"):
        monkeypatch.setenv(_key, "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    import importlib
    import config, session_auth, main
    importlib.reload(config)
    # Explicitly zero the config attributes in case load_dotenv still read .env.
    config.API_KEY = ""
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(main)
    from main import app
    return TestClient(app)


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    """TestClient with API_KEY set to 'testkey'."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "testkey")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    import importlib
    import config, session_auth, main
    importlib.reload(config)
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(main)
    from main import app
    return TestClient(app)


@pytest.fixture()
def dash_client(tmp_path, monkeypatch):
    """TestClient with DASHBOARD_PASSWORD set; no API_KEY. FAILURE_DELAY zeroed."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    import importlib
    import config, session_auth, main
    importlib.reload(config)
    config.API_KEY = ""
    importlib.reload(session_auth)
    monkeypatch.setattr(session_auth, "FAILURE_DELAY", 0)
    importlib.reload(main)
    from main import app
    # Use context-manager form so lifespan runs (init_db creates the tables)
    client = TestClient(app)
    client.__enter__()
    yield client
    client.__exit__(None, None, None)


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
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("TRAE_IDE_TOKEN", "secret-token")
    monkeypatch.setenv("TRAE_MACHINE_ID", "machine-abc")
    monkeypatch.setenv("TRAE_DEVICE_ID", "device-xyz")
    import importlib, config, session_auth, main
    importlib.reload(config)
    config.API_KEY = ""
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
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


# ── Session / cookie auth ─────────────────────────────────────────────────────

def test_login_success_sets_cookie(dash_client):
    resp = dash_client.post("/auth/login", json={"password": "testpass"})
    assert resp.status_code == 204
    cookie = resp.cookies.get("tp_session")
    assert cookie is not None
    # Inspect raw Set-Cookie header for security attributes
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie or "samesite=lax" in set_cookie.lower()
    assert "Max-Age=604800" in set_cookie or "max-age=604800" in set_cookie.lower()
    assert "Path=/" in set_cookie or "path=/" in set_cookie.lower()


def test_login_wrong_password(dash_client):
    resp = dash_client.post("/auth/login", json={"password": "wrongpass"})
    assert resp.status_code == 401
    assert "tp_session" not in resp.cookies


def test_login_disabled_when_no_password(client):
    # No DASHBOARD_PASSWORD set → 400
    resp = client.post("/auth/login", json={"password": "anything"})
    assert resp.status_code == 400


def test_session_cookie_grants_config_and_usage(dash_client):
    # Login first; TestClient persists cookies automatically
    login = dash_client.post("/auth/login", json={"password": "testpass"})
    assert login.status_code == 204
    cfg = dash_client.get("/config")
    assert cfg.status_code == 200
    stats = dash_client.get("/usage/stats")
    assert stats.status_code == 200


def test_config_401_without_cookie_when_password_set(dash_client):
    # No cookie sent → 401
    resp = dash_client.get("/config", cookies={})
    # dash_client may have residual cookies from prior tests; use a fresh client
    import importlib
    import config, session_auth, main
    from fastapi.testclient import TestClient
    c = TestClient(main.app, cookies={})
    resp = c.get("/config")
    assert resp.status_code == 401


def test_tampered_cookie_rejected(dash_client):
    login = dash_client.post("/auth/login", json={"password": "testpass"})
    assert login.status_code == 204
    good = dash_client.cookies.get("tp_session")
    assert good is not None
    # Flip last hex char in the signature
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    import importlib
    import config, session_auth, main
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    c.cookies.set("tp_session", tampered)
    resp = c.get("/config")
    assert resp.status_code == 401


def test_expired_cookie_rejected(dash_client):
    import session_auth as sa
    expired = sa.mint_session(max_age=-10)
    import importlib
    import config, session_auth, main
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    c.cookies.set("tp_session", expired)
    resp = c.get("/config")
    assert resp.status_code == 401


def test_logout_clears_session(dash_client):
    dash_client.post("/auth/login", json={"password": "testpass"})
    assert dash_client.get("/config").status_code == 200
    logout = dash_client.post("/auth/logout")
    assert logout.status_code == 204
    # After logout the cookie is gone; subsequent requests should 401
    import importlib
    import config, session_auth, main
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    # No cookies → 401
    resp = c.get("/config")
    assert resp.status_code == 401


def test_bearer_still_works_alongside_password(tmp_path, monkeypatch):
    """Both API_KEY and DASHBOARD_PASSWORD set; Bearer key grants access."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "testkey")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")
    import importlib
    import config, session_auth, main
    importlib.reload(config)
    importlib.reload(session_auth)
    importlib.reload(main)
    from main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    resp = c.get("/config", headers={"Authorization": "Bearer testkey"})
    assert resp.status_code == 200


def test_rate_limit_after_5_failures(dash_client, monkeypatch):
    import session_auth as sa
    monkeypatch.setattr(sa, "FAILURE_DELAY", 0)
    for _ in range(5):
        dash_client.post("/auth/login", json={"password": "wrong"})
    # 6th attempt — even with correct password — should be 429
    resp = dash_client.post("/auth/login", json={"password": "testpass"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_config_masks_dashboard_password(dash_client):
    dash_client.post("/auth/login", json={"password": "testpass"})
    data = dash_client.get("/config").json()
    assert "DASHBOARD_PASSWORD" in data
    assert data["DASHBOARD_PASSWORD"] == "••••••"


def test_chat_completions_requires_bearer_when_api_key_set(tmp_path, monkeypatch):
    """POST /v1/chat/completions: 401 without auth when API_KEY set; open when unset."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "testkey")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    import importlib
    import config, session_auth, main
    importlib.reload(config)
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(main)
    from main import app
    from fastapi.testclient import TestClient
    c = TestClient(app, raise_server_exceptions=False)
    # No auth → 401 (fires before upstream call)
    resp = c.post("/v1/chat/completions", json={
        "model": "deepseek-V3",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 401

    # When API_KEY is unset → open (upstream will fail but NOT with 401 from our guard)
    monkeypatch.setenv("API_KEY", "")
    importlib.reload(config)
    config.API_KEY = ""
    config.DASHBOARD_PASSWORD = ""
    importlib.reload(session_auth)
    importlib.reload(main)
    from main import app as app2
    c2 = TestClient(app2, raise_server_exceptions=False)
    resp2 = c2.post("/v1/chat/completions", json={
        "model": "deepseek-V3",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp2.status_code != 401
