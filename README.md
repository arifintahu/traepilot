# TraePilot

OpenAI-compatible proxy for Trae IDE subscription models.

> Personal use only. Bind to 127.0.0.1 only - never expose publicly.

---

## What It Does

Exposes Trae's LLMs as a standard /v1/chat/completions endpoint. Cherry Studio, Cline, Continue, and any OpenAI-compatible client can use Trae's models with zero changes.

---

## Requirements

- Python 3.9+
- Trae IDE with an active subscription

---

## Installation

    git clone https://github.com/arifintahu/traepilot.git
    cd traepilot
    python -m venv .venv
    source .venv/Scripts/activate
    pip install -r requirements.txt
    cp .env.example .env

Fill in .env. If Trae is installed locally, auto-populate most values:

    python auth.py --write

Then start:

    python main.py

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| TRAE_BASE_URL | https://coresg-normal.trae.ai | Upstream API base (varies by region; `auth.py` reports yours) |
| TRAE_IDE_TOKEN | required | Trae IDE auth token |
| TRAE_MACHINE_ID | required | Machine ID from Trae |
| TRAE_DEVICE_ID | required | Device ID from Trae |
| PROXY_HOST | 127.0.0.1 | Bind address |
| PROXY_PORT | 8787 | Bind port |
| DEFAULT_MODEL } claude-3-7-sonnet | Fallback model |
| LOG_LEVEL | INFO | Logging verbosity |

See .env.example for the full list.

---

## Getting Credentials

`TRAE_IDE_TOKEN` and the `x-*` ids come from Trae itself (requires an active, signed-in Trae). Current Trae (2.x) encrypts the account token in `storage.json`, so it can no longer be read from SQLite — `auth.py` instead reads the request headers that Trae's code-completion extension writes to its own log.

### Option A: Auto-extract (recommended)

    python auth.py            # preview: print KEY=VALUE lines for review
    python auth.py --write    # fill .env in place

`auth.py` finds Trae's newest `trae.ai-code-completion` log and takes the most recent request's headers. With `--write` it sets each matching key in `.env` in place — replacing the value, dropping duplicates, never appending — so re-running stays clean (pass a path to target a different file: `python auth.py --write path/to/.env`). It also reports the API host Trae actually talks to. If you are logged out or the token has expired, open Trae and trigger a completion or chat so it logs a fresh request, then re-run.

### Option B: Manual

**Log path** (newest session folder):
- Windows: `%APPDATA%\Trae\logs\<session>\window1\exthost\trae.ai-code-completion\completion.log`
- macOS: `~/Library/Application Support/Trae/logs/<session>/.../completion.log`
- Linux: `~/.config/Trae/logs/<session>/.../completion.log`

Find the newest line containing `request: headers: {...}` and map the header values:

- `x-ide-token` → `TRAE_IDE_TOKEN`
- `x-machine-id` → `TRAE_MACHINE_ID`
- `x-device-id` → `TRAE_DEVICE_ID`
- `x-app-id` → `TRAE_APP_ID`

> The IDE token rotates. If Trae logs you out or rotates it, re-run `auth.py` and update `.env`.

> The host in those logs (e.g. `https://coresg-normal.trae.ai`) is the real upstream. The default `TRAE_BASE_URL` may differ — if model/chat calls fail, set `TRAE_BASE_URL` to the host `auth.py` reports.

---

## Usage

Point any OpenAI-compatible client at http://127.0.0.1:8787/v1.

- Cherry Studio: Settings -> AI Provider -> OpenAI -> Base URL: http://127.0.0.1:8787/v1
- Cline / Continue: set apiBaseUrl to http://127.0.0.1:8787/v1

---

## Tests

    pytest

---

## Project Structure

    traepilot/
        main.py           # FastAPI awp: /v1/chat/completions, /v1/models, /health
        trae_client.py    # Trae upstream client
        config.py         # Env var config
        auth.py           # Credential extractor from Trae's SQLite DB
        requirements.txt
        .env.example
        tests/
            test_trae_client.py

---

## Breakage Notice

When Trae updates, check build_trae_payload() and trae_events() in trae_client.py first.

---

## License

MIT
