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
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "")[:150]
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
