# Usage Tracking — Design Spec

**Date:** 2026-06-03
**Status:** Approved

## Overview

Add per-request usage tracking to TraePilot. Every `/v1/chat/completions` call is recorded to a local SQLite database with estimated token counts, model, status, and a short prompt preview. Three read endpoints expose stats, paginated history, and daily aggregates.

---

## 1. Data Layer — `usage.py`

New file. Owns the SQLite schema, writes, and queries. No other file touches the DB directly.

### DB file

`usage.db` in the project root (same directory as `main.py`). Overridable via `USAGE_DB` env var. Added to `.gitignore`.

### Schema

```sql
-- One row per request
CREATE TABLE IF NOT EXISTS usage_requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT    NOT NULL,        -- ISO8601, UTC
    model              TEXT    NOT NULL,
    prompt_tokens      INTEGER DEFAULT 0,       -- estimated
    completion_tokens  INTEGER DEFAULT 0,       -- estimated
    total_tokens       INTEGER DEFAULT 0,
    prompt_preview     TEXT,                    -- first 150 chars of last user message
    status             TEXT    NOT NULL,        -- "ok" | "error"
    stream             INTEGER DEFAULT 0        -- 0/1 boolean
);

CREATE INDEX IF NOT EXISTS idx_ur_ts    ON usage_requests(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ur_model ON usage_requests(model);

-- Pre-aggregated daily rollup — updated atomically on each write
CREATE TABLE IF NOT EXISTS usage_daily (
    date_key          TEXT    PRIMARY KEY,      -- "2026-06-03"
    requests          INTEGER DEFAULT 0,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens      INTEGER DEFAULT 0
);
```

### Token estimation

Identical to 9router's approach — character-based `÷ 4` heuristic, no extra dependencies:

- **Input:** `ceil(len(json.dumps(messages)) / 4)`
- **Output:** `max(1, floor(len(output_text) / 4))`

All API responses include `"estimated": true` to be transparent about this.

### Public functions

| Function | Purpose |
|---|---|
| `init_db()` | Create tables + indexes. Called once at startup. |
| `record_usage(model, messages, output_text, status, stream)` | Write both tables in one transaction. |
| `get_stats(period)` | Aggregate over `"24h"` / `"7d"` / `"30d"` / `"all"`. |
| `get_history(limit, offset)` | Paginated rows, newest first. |
| `get_daily(days)` | Last N days of daily rollups. |

`record_usage` is defined `async` (uses `asyncio.get_event_loop().run_in_executor` to keep the SQLite writes off the async event loop without blocking it).

---

## 2. Integration — `main.py`

`trae_client.py` is **not modified**. All tracking happens in `main.py`'s handlers.

### Startup

`init_db()` called via FastAPI `lifespan` context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="TraePilot", version="1.0.0", lifespan=lifespan)
```

### Non-streaming handler

```python
result = await non_stream_completion(messages, req.model, req.max_tokens)
output_text = result["choices"][0]["message"]["content"]
await record_usage(req.model, messages, output_text, "ok", stream=False)
return JSONResponse(result)
```

On exception: `record_usage(..., output_text="", status="error", stream=False)` called in `except` block before re-raising.

### Streaming handler

`event_stream()` accumulates delta content from parsed SSE chunks, then calls `record_usage()` in a `finally` block — guarantees recording even if the client disconnects mid-stream:

```python
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
                accumulated.append(delta)
            except Exception:
                pass
    except Exception as e:
        status = "error"
        err = {"error": {"message": str(e), "type": "upstream_error"}}
        yield f"data: {json.dumps(err)}\n\n"
    finally:
        await record_usage(req.model, messages, "".join(accumulated), status, stream=True)
```

---

## 3. API Endpoints

Three `GET` endpoints on an `APIRouter` prefixed `/usage`. Auth: same `API_KEY` check as `/v1/chat/completions` — if `API_KEY` is set in `.env`, all usage endpoints require `Authorization: Bearer <key>`.

### `GET /usage/stats`

Query param: `period` — `24h` | `7d` | `30d` | `all` (default `24h`).

```json
{
  "period": "7d",
  "total_requests": 142,
  "total_prompt_tokens": 28400,
  "total_completion_tokens": 14200,
  "total_tokens": 42600,
  "estimated": true,
  "by_model": {
    "deepseek-V3": {"requests": 89, "prompt_tokens": 17800, "completion_tokens": 8900},
    "gpt-4o":      {"requests": 53, "prompt_tokens": 10600, "completion_tokens": 5300}
  }
}
```

### `GET /usage/history`

Query params: `limit` (default 50, max 500), `offset` (default 0).

```json
{
  "total": 142,
  "offset": 0,
  "limit": 50,
  "estimated": true,
  "items": [
    {
      "id": 142,
      "timestamp": "2026-06-03T21:34:07Z",
      "model": "deepseek-V3",
      "prompt_tokens": 124,
      "completion_tokens": 89,
      "total_tokens": 213,
      "prompt_preview": "Reply with exactly: TraePilot works",
      "status": "ok",
      "stream": true
    }
  ]
}
```

### `GET /usage/daily`

Query param: `days` (default 30, max 365).

```json
{
  "days": 30,
  "estimated": true,
  "items": [
    {"date": "2026-06-03", "requests": 24, "prompt_tokens": 4800, "completion_tokens": 2400, "total_tokens": 7200},
    {"date": "2026-06-02", "requests": 18, "prompt_tokens": 3600, "completion_tokens": 1800, "total_tokens": 5400}
  ]
}
```

Invalid `limit` / `days` values return `422 Unprocessable Entity`.

---

## 4. Files Changed

| File | Change |
|---|---|
| `usage.py` | **New** — DB layer (schema, write, queries) |
| `main.py` | Add `lifespan`, import `usage`, wire tracking into both handlers, add `usage_router` |
| `.env.example` | Add `USAGE_DB=` (optional, commented) |
| `.gitignore` | Add `usage.db` |
| `README.md` | Add "Usage tracking" section with curl examples |

No changes to `trae_client.py`, `config.py`, or `auth.py`.

---

## 5. curl Test Examples

```bash
# stats for the last 7 days
curl http://127.0.0.1:8787/usage/stats?period=7d

# last 20 requests
curl "http://127.0.0.1:8787/usage/history?limit=20"

# daily breakdown for the past week
curl "http://127.0.0.1:8787/usage/daily?days=7"
```

With `API_KEY` set:
```bash
curl -H "Authorization: Bearer <key>" http://127.0.0.1:8787/usage/stats
```
