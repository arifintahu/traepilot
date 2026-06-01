# TraePilot

OpenAI-compatible proxy for Trae IDE subscription models.

> Personal use only. Bind to 127.0.0.1 only - never expose publicly.

---

## What It Does

Exposes Trae's subscription models as a standard OpenAI-compatible API. Point Cherry Studio, Cline, Continue, or any OpenAI client at it and use Trae's models — `/v1/chat/completions` (streaming and non-streaming) and `/v1/models`.

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

Pick a working model id from `/v1/models` (e.g. `deepseek-V3`, `gpt-4o`, `gemini_2.5_flash`).

---

## Test with curl

With the server running (`python main.py`):

```bash
# health check
curl http://127.0.0.1:8787/health

# list available models
curl http://127.0.0.1:8787/v1/models

# chat — non-streaming
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Hello in 5 words"}]}'

# chat — streaming (token-by-token, ends with [DONE])
curl -N http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

If `API_KEY` is set in `.env`, add `-H "Authorization: Bearer <your-key>"`. On Windows PowerShell, use `curl.exe` (the `curl` alias there is `Invoke-WebRequest`, which has different syntax).

---

## Tests

    pytest

---

## Project Structure

    traepilot/
        main.py           # FastAPI app: /v1/chat/completions, /v1/models, /health
        trae_client.py    # Trae upstream client (chat + models)
        config.py         # Env var config
        auth.py           # Credential extractor (reads Trae's completion log)
        requirements.txt
        .env.example
        tests/
            test_trae_client.py

---

## Known limitations

- **Some models may be unavailable to your account.** Chat uses Trae's `/api/ide/v1/chat` endpoint; a model your subscription/region doesn't grant returns an error. On the test account the Claude models (`claude3.5`, `aws_sdk_claude37_sonnet`) return code `4023`, while Gemini, GPT-4.x / GPT-4o, and DeepSeek all work.
- **`/v1/models` is the legacy catalog.** It lists Trae's reachable `api/ide/v1/model_list` models (`claude3.5`, `gemini-2.5-pro`, `gpt-4.1`, `gpt-4o`, `deepseek-V3/R1`, …). Newer models shown in the Trae IDE (GPT-5.x, MiniMax, Gemini-3) are served by the IDE's native agent (`get_model_list`, not a reachable HTTP route), so they aren't listed — and `/api/ide/v1/chat` only accepts the legacy models.
- **The chat protocol is internal.** It's a prompt-pipeline request reverse-engineered from Trae's client, not a public API — a Trae update can change it.

## Breakage Notice

When Trae updates, check `build_trae_payload()` and the SSE parsing in trae_client.py (chat protocol), then the headers and credential extraction in auth.py.

---

## License

MIT
