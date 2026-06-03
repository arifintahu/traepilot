# Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every `/v1/chat/completions` request to a local SQLite DB and expose three read endpoints — `/usage/stats`, `/usage/history`, `/usage/daily`.

**Architecture:** New `usage.py` owns the DB layer (schema, write, queries). `main.py` imports from it: `init_db()` runs at startup via lifespan, `record_usage()` is awaited inside both chat handlers, and three `APIRouter` endpoints expose the read views. Token counts are estimated via the `÷ 4` char heuristic (no new deps).

**Tech Stack:** Python 3.10, FastAPI, SQLite (stdlib `sqlite3`), `asyncio.to_thread`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `usage.py` | **Create** | DB schema, write, queries |
| `tests/test_usage.py` | **Create** | Unit tests for `usage.py` |
| `tests/test_usage_integration.py` | **Create** | Integration tests for wiring in `main.py` |
| `main.py` | **Modify** | Lifespan, import usage, wire into handlers, add router |
| `.gitignore` | **Modify** | Add `usage.db*` |
| `.env.example` | **Modify** | Add `USAGE_DB=` comment |
| `README.md` | **Modify** | Add Usage Tracking section |

---

## Task 1: Unit tests for `usage.py`

**Files:**
- Create: `tests/test_usage.py`

- [ ] **Step 1: Write all failing unit tests**

Create `tests/test_usage.py`:

```python
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
```

- [ ] **Step 2: Run tests — confirm all fail with ModuleNotFoundError**

```
pytest tests/test_usage.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'usage'` (or similar collection error).

---

## Task 2: Implement `usage.py`

**Files:**
- Create: `usage.py`

- [ ] **Step 1: Create `usage.py`**

```python
"""
usage.py — SQLite-backed request usage tracking for TraePilot.

Public API:
  init_db()                                         → None   (call once at startup)
  record_usage(model, messages, output_text,        → None   (async, call after each request)
               status, stream)
  get_stats(period="24h")                           → dict
  get_history(limit=50, offset=0)                   → dict
  get_daily(days=30)                                → dict

Token counts are estimated via the ÷4 char heuristic and marked estimated=True.
DB file defaults to usage.db; override with USAGE_DB env var.
"""
import asyncio
import json
import math
import os
import sqlite3
from datetime import datetime, timezone, timedelta


def _db_path() -> str:
    """Read USAGE_DB env var on every call so tests can override without reloading."""
    return os.getenv("USAGE_DB", "usage.db")


def init_db() -> None:
    """Create tables and indexes if they don't exist. Safe to call multiple times."""
    with sqlite3.connect(_db_path()) as conn:
        conn.executescript("""
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;

            CREATE TABLE IF NOT EXISTS usage_requests (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp          TEXT    NOT NULL,
                model              TEXT    NOT NULL,
                prompt_tokens      INTEGER DEFAULT 0,
                completion_tokens  INTEGER DEFAULT 0,
                total_tokens       INTEGER DEFAULT 0,
                prompt_preview     TEXT,
                status             TEXT    NOT NULL,
                stream             INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_ur_ts    ON usage_requests(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_ur_model ON usage_requests(model);

            CREATE TABLE IF NOT EXISTS usage_daily (
                date_key          TEXT    PRIMARY KEY,
                requests          INTEGER DEFAULT 0,
                prompt_tokens     INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens      INTEGER DEFAULT 0
            );
        """)


def _estimate_tokens_in(messages: list) -> int:
    return math.ceil(len(json.dumps(messages)) / 4)


def _estimate_tokens_out(output_text: str) -> int:
    return max(1, math.floor(len(output_text) / 4)) if output_text else 0


def _prompt_preview(messages: list) -> str:
    """Return first 150 chars of the last user message, or empty string."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                return content[:150]
    return ""


def _record_usage_sync(
    model: str, messages: list, output_text: str, status: str, stream: bool
) -> None:
    """Synchronous write — run via asyncio.to_thread so it doesn't block the event loop."""
    prompt_tokens     = _estimate_tokens_in(messages)
    completion_tokens = _estimate_tokens_out(output_text)
    total_tokens      = prompt_tokens + completion_tokens
    preview           = _prompt_preview(messages)

    now_utc   = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_key  = now_utc.strftime("%Y-%m-%d")

    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO usage_requests
                (timestamp, model, prompt_tokens, completion_tokens,
                 total_tokens, prompt_preview, status, stream)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, model, prompt_tokens, completion_tokens,
             total_tokens, preview, status, 1 if stream else 0),
        )
        conn.execute(
            """
            INSERT INTO usage_daily
                (date_key, requests, prompt_tokens, completion_tokens, total_tokens)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(date_key) DO UPDATE SET
                requests          = requests + 1,
                prompt_tokens     = prompt_tokens + excluded.prompt_tokens,
                completion_tokens = completion_tokens + excluded.completion_tokens,
                total_tokens      = total_tokens + excluded.total_tokens
            """,
            (date_key, prompt_tokens, completion_tokens, total_tokens),
        )


async def record_usage(
    model: str, messages: list, output_text: str, status: str, stream: bool
) -> None:
    """Async wrapper: runs the SQLite write in a thread pool."""
    await asyncio.to_thread(
        _record_usage_sync, model, messages, output_text, status, stream
    )


def get_stats(period: str = "24h") -> dict:
    """Return aggregate token/request counts for the given period.

    period: "24h" | "7d" | "30d" | "all"  (unknown values treated as "24h")
    """
    _periods = {
        "24h": timedelta(hours=24),
        "7d":  timedelta(days=7),
        "30d": timedelta(days=30),
        "all": None,
    }
    delta = _periods.get(period, timedelta(hours=24))

    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        if delta is not None:
            cutoff = (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows = conn.execute(
                """
                SELECT model,
                       COUNT(*)               AS requests,
                       SUM(prompt_tokens)     AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens
                FROM usage_requests
                WHERE timestamp >= ?
                GROUP BY model
                """,
                (cutoff,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT model,
                       COUNT(*)               AS requests,
                       SUM(prompt_tokens)     AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens
                FROM usage_requests
                GROUP BY model
                """
            ).fetchall()

    by_model: dict = {}
    total_requests = total_prompt = total_completion = 0

    for row in rows:
        pt = row["prompt_tokens"] or 0
        ct = row["completion_tokens"] or 0
        by_model[row["model"]] = {
            "requests":          row["requests"],
            "prompt_tokens":     pt,
            "completion_tokens": ct,
        }
        total_requests   += row["requests"]
        total_prompt     += pt
        total_completion += ct

    return {
        "period":                  period,
        "total_requests":          total_requests,
        "total_prompt_tokens":     total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens":            total_prompt + total_completion,
        "estimated":               True,
        "by_model":                by_model,
    }


def get_history(limit: int = 50, offset: int = 0) -> dict:
    """Return paginated request rows, newest first."""
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            "SELECT COUNT(*) FROM usage_requests"
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, timestamp, model, prompt_tokens, completion_tokens,
                   total_tokens, prompt_preview, status, stream
            FROM usage_requests
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return {
        "total":     total,
        "offset":    offset,
        "limit":     limit,
        "estimated": True,
        "items": [
            {
                "id":                row["id"],
                "timestamp":         row["timestamp"],
                "model":             row["model"],
                "prompt_tokens":     row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_tokens":      row["total_tokens"],
                "prompt_preview":    row["prompt_preview"],
                "status":            row["status"],
                "stream":            bool(row["stream"]),
            }
            for row in rows
        ],
    }


def get_daily(days: int = 30) -> dict:
    """Return pre-aggregated daily rollups for the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT date_key, requests, prompt_tokens, completion_tokens, total_tokens
            FROM usage_daily
            WHERE date_key >= ?
            ORDER BY date_key DESC
            """,
            (cutoff,),
        ).fetchall()

    return {
        "days":      days,
        "estimated": True,
        "items": [
            {
                "date":              row["date_key"],
                "requests":          row["requests"],
                "prompt_tokens":     row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_tokens":      row["total_tokens"],
            }
            for row in rows
        ],
    }
```

- [ ] **Step 2: Run tests — confirm all pass**

```
pytest tests/test_usage.py -v
```

Expected: all tests pass. Example output:
```
tests/test_usage.py::test_init_db_creates_usage_requests_table PASSED
tests/test_usage.py::test_init_db_creates_usage_daily_table PASSED
tests/test_usage.py::test_init_db_is_idempotent PASSED
...
27 passed in 0.XXs
```

- [ ] **Step 3: Commit**

```
git add usage.py tests/test_usage.py
git commit -m "feat: add usage DB layer (usage.py) with unit tests"
```

---

## Task 3: Integration tests for `main.py` wiring

**Files:**
- Create: `tests/test_usage_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_usage_integration.py`:

```python
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
def client():
    """TestClient with init_db patched out so no usage.db is created."""
    with patch("main.init_db"), TestClient(main_module.app) as c:
        yield c


# ── non-streaming: record_usage called with correct args ──────────────────────

def test_non_stream_records_ok_on_success(client):
    with patch("main.non_stream_completion", new=AsyncMock(return_value=_NON_STREAM_RESULT)), \
         patch("main.record_usage", new=AsyncMock()) as mock_record:
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
    with patch("main.non_stream_completion", new=AsyncMock(side_effect=RuntimeError("fail"))), \
         patch("main.record_usage", new=AsyncMock()) as mock_record:
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
    with patch("main.stream_completion", new=_fake_stream), \
         patch("main.record_usage", new=AsyncMock()) as mock_record:
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
    with patch("main.get_stats", return_value={
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
    with patch("main.get_stats", side_effect=fake_get_stats):
        client.get("/usage/stats")
    assert captured["period"] == "24h"


# ── /usage/history ────────────────────────────────────────────────────────────

def test_history_endpoint_returns_200(client):
    with patch("main.get_history", return_value={
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
    with patch("main.get_daily", return_value={
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
```

- [ ] **Step 2: Run tests — confirm they fail**

```
pytest tests/test_usage_integration.py -v 2>&1 | head -30
```

Expected: failures because `main.py` doesn't import `record_usage`, `get_stats`, etc., and doesn't have the usage router.

---

## Task 4: Modify `main.py`

**Files:**
- Modify: `main.py` (full replacement)

- [ ] **Step 1: Replace `main.py` with the wired version**

```python
import time
import json
from contextlib import asynccontextmanager
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import BIND_HOST, BIND_PORT, API_KEY
from trae_client import stream_completion, non_stream_completion, list_models
from usage import init_db, record_usage, get_stats, get_history, get_daily


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TraePilot", version="1.0.0", lifespan=lifespan)
security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials | None = None) -> None:
    if not API_KEY:
        return
    if not credentials or credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False
    max_tokens: Optional[int] = None


@app.get("/v1/models")
async def get_models():
    try:
        models = await list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    if req.stream:
        async def event_stream():
            accumulated = []
            status = "ok"
            try:
                async for chunk in stream_completion(messages, req.model, req.max_tokens):
                    if chunk == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    yield chunk
                    try:
                        delta = json.loads(chunk[6:])["choices"][0]["delta"].get("content", "")
                        if delta:
                            accumulated.append(delta)
                    except Exception:
                        pass
            except Exception as e:
                status = "error"
                err = {"error": {"message": str(e), "type": "upstream_error"}}
                yield f"data: {json.dumps(err)}\n\n"
            finally:
                await record_usage(
                    req.model, messages, "".join(accumulated), status, stream=True
                )
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        result = await non_stream_completion(messages, req.model, req.max_tokens)
    except Exception as e:
        await record_usage(req.model, messages, "", "error", stream=False)
        raise HTTPException(status_code=502, detail=str(e))

    output_text = result["choices"][0]["message"]["content"]
    await record_usage(req.model, messages, output_text, "ok", stream=False)
    return JSONResponse(result)


# ── Usage API ──────────────────────────────────────────────────────────────────

usage_router = APIRouter(prefix="/usage", tags=["usage"])


@usage_router.get("/stats")
async def usage_stats(
    period: Literal["24h", "7d", "30d", "all"] = "24h",
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_stats(period)


@usage_router.get("/history")
async def usage_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_history(limit, offset)


@usage_router.get("/daily")
async def usage_daily(
    days: int = Query(default=30, ge=1, le=365),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_daily(days)


app.include_router(usage_router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
```

- [ ] **Step 2: Run integration tests — confirm all pass**

```
pytest tests/test_usage_integration.py -v
```

Expected: all tests pass:
```
tests/test_usage_integration.py::test_non_stream_records_ok_on_success PASSED
tests/test_usage_integration.py::test_non_stream_records_error_when_completion_raises PASSED
tests/test_usage_integration.py::test_stream_records_ok_and_accumulates_content PASSED
tests/test_usage_integration.py::test_stats_endpoint_returns_200 PASSED
...
12 passed in 0.XXs
```

- [ ] **Step 3: Run full test suite — confirm no regressions**

```
pytest tests/ -v
```

Expected: all tests pass (the existing `test_trae_client.py` tests may already fail due to a pre-existing mismatch between those tests and the current `trae_client.py` — that is out of scope for this plan).

- [ ] **Step 4: Commit**

```
git add main.py tests/test_usage_integration.py
git commit -m "feat: wire usage tracking into main.py with /usage/* endpoints"
```

---

## Task 5: Config, .gitignore, README

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add `usage.db*` to `.gitignore`**

Open `.gitignore` and append three lines at the end:

```
usage.db
usage.db-wal
usage.db-shm
```

(WAL mode creates `-wal` and `-shm` side files alongside `usage.db`.)

- [ ] **Step 2: Add `USAGE_DB` to `.env.example`**

After the `API_KEY=` line, add:

```

# Optional: path for the usage tracking SQLite DB (default: usage.db in project root)
# USAGE_DB=usage.db
```

- [ ] **Step 3: Add Usage Tracking section to README**

After the "Test with curl" section (before `## Tests`), add:

```markdown
---

## Usage Tracking

Every `/v1/chat/completions` request is recorded to `usage.db` (SQLite, created automatically). Token counts are estimated via the ÷4 character heuristic and marked `"estimated": true`.

```bash
# Summary for the last 7 days
curl "http://127.0.0.1:8787/usage/stats?period=7d"

# Last 20 requests with prompt preview
curl "http://127.0.0.1:8787/usage/history?limit=20"

# Daily breakdown for the past week
curl "http://127.0.0.1:8787/usage/daily?days=7"
```

Valid `period` values: `24h` (default) | `7d` | `30d` | `all`.
`limit` max: 500. `days` max: 365.

If `API_KEY` is set, the usage endpoints also require `Authorization: Bearer <key>`.

To store the DB at a different path, set `USAGE_DB=/path/to/usage.db` in `.env`.

---
```

- [ ] **Step 4: Commit**

```
git add .gitignore .env.example README.md
git commit -m "chore: add usage.db to gitignore, document usage tracking in README"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task that implements it |
|---|---|
| `usage.py` with `init_db`, `record_usage`, `get_stats`, `get_history`, `get_daily` | Task 2 |
| SQLite tables `usage_requests` + `usage_daily` | Task 2 |
| Token estimation `÷4` char heuristic | Task 2 (`_estimate_tokens_in`, `_estimate_tokens_out`) |
| `prompt_preview` — first 150 chars of last user message | Task 2 (`_prompt_preview`) |
| `init_db()` via lifespan context manager | Task 4 |
| Non-streaming: `record_usage` after result, `"error"` on exception | Task 4 |
| Streaming: accumulate content, `record_usage` in `finally` | Task 4 |
| `GET /usage/stats?period=` with `Literal` validation | Task 4 |
| `GET /usage/history?limit=&offset=` with `ge`/`le` validation | Task 4 |
| `GET /usage/daily?days=` with `ge`/`le` validation | Task 4 |
| Same `API_KEY` auth on usage endpoints | Task 4 (`verify_api_key` + `Depends`) |
| `usage.db` in `.gitignore` | Task 5 |
| `USAGE_DB` env var in `.env.example` | Task 5 |
| README curl examples | Task 5 |
| No changes to `trae_client.py`, `config.py`, `auth.py` | Confirmed — none of those files appear in the plan |

**Placeholder scan:** None found.

**Type consistency:** `record_usage(model, messages, output_text, status, stream)` — signature is identical in `usage.py` definition (Task 2), all call sites in `main.py` (Task 4), and all mock assertions in `test_usage_integration.py` (Task 3). `get_stats(period)`, `get_history(limit, offset)`, `get_daily(days)` match across definition and all call sites.
