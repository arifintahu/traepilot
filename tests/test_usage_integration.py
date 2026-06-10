"""
Integration tests — verify main.py calls record_usage with the right arguments
and that the /usage/* endpoints return the expected shapes.

record_usage and init_db are mocked so no real DB is created during these tests.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import main as main_module


# ── shared fixtures & data ────────────────────────────────────────────────────

_NON_STREAM_RESULT = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1000000,
    "model": "deepseek-V3",
    "choices": [{
        "index": 0,
        "message": {"role": "assistant", "content": "hello back"},
        "finish_reason": "stop",
    }],
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
}


async def _fake_stream(*args, **kwargs):
    """Async generator that mimics stream_completion output."""
    chunk = json.dumps({
        "id": "1", "object": "chat.completion.chunk", "created": 1,
        "model": "deepseek-V3",
        "choices": [{"index": 0, "delta": {"content": "hi there"}, "finish_reason": None}],
    })
    yield f"data: {chunk}\n\n"
    done_chunk = json.dumps({
        "id": "1", "object": "chat.completion.chunk", "created": 1,
        "model": "deepseek-V3",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    yield f"data: {done_chunk}\n\n"
    yield "[DONE]"


@pytest.fixture()
def client(monkeypatch):
    """TestClient with init_db patched out so no usage.db is created."""
    # Zero auth so tests don't depend on what's in .env
    monkeypatch.setattr(main_module, "API_KEY", "")
    monkeypatch.setattr(main_module, "DASHBOARD_PASSWORD", "")
    with patch("main.init_db"), TestClient(main_module.app) as c:
        yield c


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    """Patch config in deps module for auth tests."""
    import config as cfg
    monkeypatch.setattr(cfg, "API_KEY", "")
    monkeypatch.setattr(cfg, "DASHBOARD_PASSWORD", "")


# ── non-streaming: record_usage called with correct args ──────────────────────

def test_non_stream_records_ok_on_success(client):
    with patch("routes_openai.non_stream_completion", new=AsyncMock(return_value=_NON_STREAM_RESULT)), \
         patch("routes_openai.record_usage", new=AsyncMock()) as mock_record:
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-V3",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        })
    assert resp.status_code == 200
    mock_record.assert_awaited_once()
    args = mock_record.call_args.args
    assert args[0] == "deepseek-V3"  # model
    assert args[2] == "hello back"   # output_text from result
    assert args[3] == "ok"           # status
    assert args[4] is False          # stream=False


def test_non_stream_records_error_when_completion_raises(client):
    with patch("routes_openai.non_stream_completion", new=AsyncMock(side_effect=RuntimeError("fail"))), \
         patch("routes_openai.record_usage", new=AsyncMock()) as mock_record:
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-V3",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        })
    assert resp.status_code == 502
    mock_record.assert_awaited_once()
    args = mock_record.call_args.args
    assert args[2] == ""         # empty output_text
    assert args[3] == "error"    # status
    assert args[4] is False      # stream=False


# ── streaming: record_usage called after stream finishes ─────────────────────

def test_stream_records_ok_and_accumulates_content(client):
    with patch("routes_openai.stream_completion", new=_fake_stream), \
         patch("routes_openai.record_usage", new=AsyncMock()) as mock_record:
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-V3",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        })
    assert resp.status_code == 200
    mock_record.assert_awaited_once()
    args = mock_record.call_args.args
    assert args[0] == "deepseek-V3"   # model
    assert "hi there" in args[2]      # output_text accumulated from deltas
    assert args[3] == "ok"            # status
    assert args[4] is True            # stream=True


# ── /usage/stats ──────────────────────────────────────────────────────────────

def test_stats_endpoint_returns_200(client):
    with patch("routes_dashboard.get_stats", return_value={
        "period": "24h", "total_requests": 3,
        "total_prompt_tokens": 100, "total_completion_tokens": 50,
        "total_tokens": 150, "estimated": True, "by_model": {},
    }):
        resp = client.get("/usage/stats?period=24h")
    assert resp.status_code == 200
    assert resp.json()["total_requests"] == 3
    assert resp.json()["estimated"] is True


def test_stats_endpoint_rejects_invalid_period(client):
    resp = client.get("/usage/stats?period=bogus")
    assert resp.status_code == 422


def test_stats_endpoint_default_period_is_24h(client):
    captured = {}
    def fake_get_stats(period="24h"):
        captured["period"] = period
        return {"period": period, "total_requests": 0,
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_tokens": 0, "estimated": True, "by_model": {}}
    with patch("routes_dashboard.get_stats", side_effect=fake_get_stats):
        client.get("/usage/stats")
    assert captured["period"] == "24h"


# ── /usage/history ────────────────────────────────────────────────────────────

def test_history_endpoint_returns_200(client):
    with patch("routes_dashboard.get_history", return_value={
        "total": 1, "offset": 0, "limit": 50, "estimated": True,
        "items": [{
            "id": 1, "timestamp": "2026-06-03T00:00:00Z",
            "model": "gpt-4o", "prompt_tokens": 10, "completion_tokens": 5,
            "total_tokens": 15, "prompt_preview": "hi", "status": "ok", "stream": False,
        }],
    }):
        resp = client.get("/usage/history")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_history_endpoint_rejects_limit_over_500(client):
    resp = client.get("/usage/history?limit=501")
    assert resp.status_code == 422


def test_history_endpoint_rejects_negative_offset(client):
    resp = client.get("/usage/history?offset=-1")
    assert resp.status_code == 422


# ── /usage/daily ──────────────────────────────────────────────────────────────

def test_daily_endpoint_returns_200(client):
    with patch("routes_dashboard.get_daily", return_value={
        "days": 7, "estimated": True,
        "items": [{"date": "2026-06-03", "requests": 5,
                   "prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}],
    }):
        resp = client.get("/usage/daily?days=7")
    assert resp.status_code == 200
    assert resp.json()["days"] == 7


def test_daily_endpoint_rejects_days_over_365(client):
    resp = client.get("/usage/daily?days=366")
    assert resp.status_code == 422


def test_daily_endpoint_rejects_days_zero(client):
    resp = client.get("/usage/daily?days=0")
    assert resp.status_code == 422
