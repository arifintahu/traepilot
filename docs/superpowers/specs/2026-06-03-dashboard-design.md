# Dashboard Design Spec
**Date:** 2026-06-03
**Branch:** `feature/dashboard`

## Overview

A web-based admin dashboard served directly by the existing FastAPI proxy. Single HTML file, vanilla JS, no build step. Provides four sections via a sidebar nav: Usage, Models, Test Chat, and Config.

---

## Architecture

### New files
| File | Purpose |
|---|---|
| `dashboard.html` | Self-contained dashboard UI (inline CSS + JS) |

### Changed files
| File | Change |
|---|---|
| `main.py` | Add `GET /dashboard` → serves `dashboard.html` as `HTMLResponse`; add `GET /config` endpoint |

### No changes to
- `config.py`, `trae_client.py`, `usage.py`, `auth.py`

---

## New Endpoint: `GET /config`

Returns all env-derived config values. Sensitive fields are masked server-side — the real value is never sent to the browser.

**Sensitive fields (always masked):** `API_KEY`, `TRAE_IDE_TOKEN`, `TRAE_MACHINE_ID`, `TRAE_DEVICE_ID`

**Response shape:**
```json
{
  "TRAE_BASE_URL": "https://coresg-normal.trae.ai",
  "BIND_HOST": "127.0.0.1",
  "BIND_PORT": 8080,
  "API_KEY": "••••••",
  "TRAE_EXCLUDE_MODELS": "claude3.5,aws_sdk_claude37_sonnet",
  "TRAE_APP_ID": "abc123",
  "TRAE_DEVICE_BRAND": "...",
  "TRAE_DEVICE_CPU": "...",
  "TRAE_DEVICE_ID": "••••••",
  "TRAE_DEVICE_TYPE": "...",
  "TRAE_IDE_TOKEN": "••••••",
  "TRAE_IDE_VERSION": "...",
  "TRAE_IDE_VERSION_CODE": "...",
  "TRAE_MACHINE_ID": "••••••",
  "TRAE_OS_VERSION": "...",
  "TRAE_PLUGIN_CHANNEL": "icube-ai"
}
```

The reveal toggle in the UI shows `[stored in .env — not sent to browser]` for masked fields. No second request needed.

---

## Visual Design

- **Layout:** Sidebar nav (C) — persistent left sidebar, main content area
- **Theme:** Dark (`#0a0b0f` body, `#0d1117` surfaces), WCAG AA compliant throughout
- **Accent:** Indigo→blue gradient (`#818cf8` → `#60a5fa`)
- **All text colors meet WCAG AA (≥ 4.5:1):**

| Color | Role | Ratio |
|---|---|---|
| `#f0f6fc` | Primary headings | 17.4:1 |
| `#c9d1d9` | Body / table cells | 11.6:1 |
| `#8b949e` | Muted labels, meta | 6.5:1 |
| `#818cf8` | Accent / active nav | 6.9:1 |
| `#34d399` | Success badge | 11.5:1 |

- Chart legend uses **shape + color** (round = Requests, square = Tokens) — not color alone

---

## Section: Usage (default view)

**Data sources:**
- `GET /usage/stats?period={24h|7d|30d|all}` — stat cards + model table
- `GET /usage/daily?days=7` — bar chart (always 7 days)

**UI elements:**
1. **Period tabs** — 24h (default) / 7d / 30d / All; switching refetches stats
2. **Stat cards (×4):** Requests, Total Tokens, Prompt Tokens, Completion Tokens
3. **Bar chart:** Grouped SVG bars — Requests + Tokens÷1k per day, with date x-axis; today highlighted
4. **Model breakdown table:** columns — Model, Requests, Prompt Tokens, Completion Tokens, Share (inline gradient bar + %)

**Loading:** Period tab switch shows loading overlay on cards + chart only; table stays until new data arrives.

---

## Section: Models

**Data source:** `GET /v1/models`

**UI elements:**
- Card grid — one card per model showing `id`, `owned_by`
- Copy-to-clipboard button on each card (copies model ID)
- Refresh button — re-fetches live from Trae

---

## Section: Test Chat

**Behavior:**
1. On page load, fetches `/v1/models` to get the first available model
2. Single `▶ Run Test` button — sends:
   ```json
   POST /v1/chat/completions
   { "model": "<first-model>", "messages": [{"role":"user","content":"Hello! Are you working?"}], "stream": false }
   ```
3. Result box shows: response text, model used, latency in ms
4. Button states: idle → loading spinner → success (green check) / error (red ✕)

---

## Section: Config

**Data source:** `GET /config`

**UI elements:**
- Two-column key/value table
- Sensitive fields: display `••••••` with a 👁 reveal toggle that switches to `[stored in .env — not sent to browser]`
- Non-sensitive fields: plain text

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Any fetch fails | Inline banner `⚠ Failed to load` + Retry button |
| Test Chat error | Button turns red, error message shown below |
| `/v1/models` unavailable at Test Chat load | Button disabled, tooltip: `"Could not load models"` |
| 401 (API_KEY set) | Full-page API key prompt on load; key stored in `sessionStorage`; sent as `Authorization: Bearer <key>` on all requests |
| No API_KEY configured | No auth prompt |

---

## Auth Flow

`GET /health` has no auth guard in the current codebase, so it cannot signal whether a key is required. Instead:

- Dashboard makes `GET /config` as its first fetch (this endpoint will require `verify_api_key`)
- **401 received:** render full-page key entry form, store key in `sessionStorage`, re-fetch `/config`
- **200 received:** render dashboard normally
- All subsequent `fetch()` calls attach the stored key as `Authorization: Bearer <key>`

`GET /config` must use the same `Depends(security)` + `verify_api_key` pattern as the existing usage endpoints.

---

## Out of Scope

- Real-time streaming updates (dashboard is pull-based, manual refresh)
- Edit/write config from the dashboard
- User management or multi-user auth
- Mobile layout optimization
