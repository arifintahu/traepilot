"""Unit tests for usage.py — SQLite DB layer."""
import asyncio
import json
import math
import sqlite3
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

def make_messages(text: str = "hello") -> list:
    return [{"role": "user", "content": text}]


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def u(tmp_path, monkeypatch):
    """Fresh usage module backed by a temp DB for each test."""
    monkeypatch.setenv("USAGE_DB", str(tmp_path / "test.db"))
    import importlib
    import usage
    importlib.reload(usage)
    usage.init_db()
    return usage


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_usage_requests_table(u, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "usage_requests" in names


def test_init_db_creates_usage_daily_table(u, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "usage_daily" in names


def test_init_db_is_idempotent(u):
    """Calling init_db twice must not raise."""
    u.init_db()


# ── record_usage ──────────────────────────────────────────────────────────────

def test_record_usage_inserts_row(u, tmp_path):
    run(u.record_usage("deepseek-V3", make_messages("hi"), "hello", "ok", False))
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM usage_requests").fetchone()
    conn.close()
    assert row["model"] == "deepseek-V3"
    assert row["status"] == "ok"
    assert row["stream"] == 0


def test_record_usage_captures_prompt_preview(u):
    run(u.record_usage("gpt-4o", make_messages("tell me a joke"), "ha ha", "ok", False))
    result = u.get_history(1, 0)
    assert result["items"][0]["prompt_preview"] == "tell me a joke"


def test_record_usage_truncates_preview_to_150_chars(u):
    long_msg = "a" * 300
    run(u.record_usage("gpt-4o", make_messages(long_msg), "resp", "ok", False))
    result = u.get_history(1, 0)
    assert result["items"][0]["prompt_preview"] == "a" * 150


def test_record_usage_estimates_prompt_tokens(u):
    msgs = make_messages("hello")
    run(u.record_usage("gpt-4o", msgs, "hi", "ok", False))
    expected = math.ceil(len(json.dumps(msgs)) / 4)
    assert u.get_history(1, 0)["items"][0]["prompt_tokens"] == expected


def test_record_usage_estimates_completion_tokens(u):
    output = "response text here"
    run(u.record_usage("gpt-4o", make_messages("hi"), output, "ok", False))
    expected = max(1, math.floor(len(output) / 4))
    assert u.get_history(1, 0)["items"][0]["completion_tokens"] == expected


def test_record_usage_records_error_status(u):
    run(u.record_usage("gpt-4o", make_messages("hi"), "", "error", False))
    assert u.get_history(1, 0)["items"][0]["status"] == "error"


def test_record_usage_records_stream_true(u):
    run(u.record_usage("gpt-4o", make_messages("hi"), "resp", "ok", True))
    assert u.get_history(1, 0)["items"][0]["stream"] is True


def test_record_usage_writes_daily_rollup(u, tmp_path):
    run(u.record_usage("gpt-4o", make_messages("hi"), "resp", "ok", False))
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    row = conn.execute("SELECT requests FROM usage_daily").fetchone()
    conn.close()
    assert row[0] == 1


def test_record_usage_accumulates_daily_on_repeated_calls(u, tmp_path):
    for _ in range(3):
        run(u.record_usage("gpt-4o", make_messages("hi"), "resp", "ok", False))
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    row = conn.execute("SELECT requests FROM usage_daily").fetchone()
    conn.close()
    assert row[0] == 3


# ── get_stats ─────────────────────────────────────────────────────────────────

def test_get_stats_returns_zero_when_empty(u):
    result = u.get_stats("24h")
    assert result["total_requests"] == 0
    assert result["by_model"] == {}
    assert result["estimated"] is True


def test_get_stats_counts_requests_by_model(u):
    run(u.record_usage("deepseek-V3", make_messages("hi"), "resp", "ok", False))
    run(u.record_usage("deepseek-V3", make_messages("hi"), "resp", "ok", False))
    run(u.record_usage("gpt-4o",      make_messages("hi"), "resp", "ok", False))
    result = u.get_stats("all")
    assert result["by_model"]["deepseek-V3"]["requests"] == 2
    assert result["by_model"]["gpt-4o"]["requests"] == 1
    assert result["total_requests"] == 3


def test_get_stats_totals_are_sum_of_models(u):
    run(u.record_usage("deepseek-V3", make_messages("hi"), "resp", "ok", False))
    run(u.record_usage("gpt-4o",      make_messages("hi"), "resp", "ok", False))
    result = u.get_stats("all")
    model_total = sum(v["prompt_tokens"] for v in result["by_model"].values())
    assert result["total_prompt_tokens"] == model_total


def test_get_stats_unknown_period_falls_back_to_24h(u):
    """Unknown period strings must not raise."""
    result = u.get_stats("bogus")
    assert "total_requests" in result


# ── get_history ───────────────────────────────────────────────────────────────

def test_get_history_empty_when_no_records(u):
    result = u.get_history(50, 0)
    assert result["total"] == 0
    assert result["items"] == []


def test_get_history_returns_newest_first(u):
    run(u.record_usage("gpt-4o", make_messages("first"),  "resp", "ok", False))
    run(u.record_usage("gpt-4o", make_messages("second"), "resp", "ok", False))
    result = u.get_history(10, 0)
    assert result["items"][0]["prompt_preview"] == "second"


def test_get_history_pagination(u):
    for i in range(5):
        run(u.record_usage("gpt-4o", make_messages(f"msg{i}"), "resp", "ok", False))
    result = u.get_history(2, 2)
    assert len(result["items"]) == 2
    assert result["total"] == 5
    assert result["offset"] == 2
    assert result["limit"] == 2


# ── get_daily ─────────────────────────────────────────────────────────────────

def test_get_daily_returns_today_when_request_recorded(u):
    run(u.record_usage("gpt-4o", make_messages("hi"), "resp", "ok", False))
    result = u.get_daily(1)
    assert len(result["items"]) == 1
    assert result["items"][0]["requests"] == 1


def test_get_daily_days_param_in_response(u):
    result = u.get_daily(7)
    assert result["days"] == 7
    assert result["estimated"] is True


def test_get_daily_empty_when_no_records(u):
    result = u.get_daily(30)
    assert result["items"] == []
