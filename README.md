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
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Fill in .env. If Trae is installed locally, auto-populate most values:

    python auth.py >> .env

Then start:

    python main.py

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| TRAE_BASE_URL | https://trae-api-sg.mchost.guru | Upstream API base |
| TRAE_IDE_TOKEN | required | Trae IDE auth token |
| TRAE_MACHINE_ID | required | Machine ID from Trae |
| TRAE_DEVICE_ID | required | Device ID from Trae |
| PROXY_HOST | 127.0.0.1 | Bind address |
| PROXY_PORT | 8080 | Bind port |
| DEFAULT_MODEL } claude-3-7-sonnet | Fallback model |
| LOG_LEVEL | INFO | Logging verbosity |

See .env.example for the full list.

---

## Usage

Point any OpenAI-compatible client at http://127.0.0.1:8080/v1.

- Cherry Studio: Settings -> AI Provider -> OpenAI -> Base URL: http://127.0.0.1:8080/v1
- Cline / Continue: set apiBaseUrl to http://127.0.0.1:8080/v1

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
