# 🛩️ TraePilot

**Use your Trae IDE subscription with any OpenAI-compatible client.**

Point Cherry Studio, Cline, Continue, or any OpenAI client at `http://127.0.0.1:8787/v1` and chat with Trae's models — no API key required, no extra cost.

> ⚠️ **Personal use only.** Binds to `127.0.0.1` — never expose publicly.

---

## 🤔 Why TraePilot?

Trae IDE has a great model subscription but locks you into its own chat UI. TraePilot bridges the gap:

| Without TraePilot | With TraePilot |
|---|---|
| ❌ Trae models only in Trae's UI | ✅ Use Trae models in any client |
| ❌ Can't use Cline / Continue / Cherry Studio | ✅ Drop-in OpenAI-compatible API |
| ❌ No usage visibility | ✅ Local SQLite usage tracking |

---

## 📋 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.10+ | 3.10 minimum — uses `X \| Y` union types and `list[T]` generics |
| **Trae IDE** | 2.x | Must be installed, signed in, and have an active subscription |
| **Git** | any | For cloning the repo |

> 💡 Python 3.9 and below are not supported. Check your version with `python --version`.

---

## 🚀 Quick Start

**1. Clone and install**
```bash
git clone https://github.com/arifintahu/traepilot.git
cd traepilot
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

**2. Pull credentials from Trae**
```bash
python auth.py --write
```

> 💡 `auth.py` reads your credentials directly from Trae's own completion logs — no manual token hunting. If it reports a different `TRAE_BASE_URL` than the default, update your `.env`.

**3. Start the proxy**
```bash
python main.py
```

That's it. Proxy is live at `http://127.0.0.1:8787/v1`.

---

## 🔌 Connect Your Client

Point any OpenAI-compatible client at:

```
Base URL:  http://127.0.0.1:8787/v1
API Key:   (leave empty, or set API_KEY in .env for local auth)
```

| Client | Where to set it |
|---|---|
| **Cherry Studio** | Settings → AI Provider → OpenAI → Base URL |
| **Cline** | Settings → API Provider → OpenAI Compatible → Base URL |
| **Continue** | `config.json` → `apiBase` |
| **Cursor** | Settings → OpenAI API → Base URL (override) |
| **Any OpenAI SDK** | `base_url="http://127.0.0.1:8787/v1"` |

---

## 🤖 Available Models

Fetch the live list anytime:
```bash
curl http://127.0.0.1:8787/v1/models
```

Working models (verified against the API):

| Model ID | Notes |
|---|---|
| `deepseek-V3` | ✅ Recommended default |
| `deepseek-V3-0324` | ✅ |
| `deepseek-R1` | ✅ Reasoning model |
| `gpt-4o` | ✅ |
| `gpt-4.1-2025-04-14` | ✅ |
| `gemini-2.5-pro-preview-03-25` | ✅ |
| `gemini_2.5_flash` | ✅ |
| `claude3.5` | ⚠️ May return 4023 (account/region) |
| `aws_sdk_claude37_sonnet` | ⚠️ May return 4023 (account/region) |

> ℹ️ **Newer models** (GPT-5.x, Gemini-3, MiniMax, Kimi…) shown in Trae IDE cannot be proxied — their requests are encrypted at the application layer via ByteDance's "aha" transport. `/v1/models` lists only what's actually reachable.

---

## 🔑 Getting Credentials

Trae 2.x encrypts the account token, so `auth.py` reads it from Trae's own request logs instead of the database.

### Auto-extract (recommended)

```bash
python auth.py            # preview what will be written
python auth.py --write    # write directly into .env
```

`--write` updates `.env` in-place — replaces values, drops duplicates, never appends. Safe to re-run after token rotation.

**If the token expires:** Open Trae, trigger any completion or chat (so it logs a fresh request), then re-run `python auth.py --write`.

### Manual extract

Find the newest session log:
- **Windows:** `%APPDATA%\Trae\logs\<session>\window1\exthost\trae.ai-code-completion\completion.log`
- **macOS:** `~/Library/Application Support/Trae/logs/<session>/.../completion.log`
- **Linux:** `~/.config/Trae/logs/<session>/.../completion.log`

Search for `request: headers: {...}` and map:

```
x-ide-token   → TRAE_IDE_TOKEN
x-machine-id  → TRAE_MACHINE_ID
x-device-id   → TRAE_DEVICE_ID
x-app-id      → TRAE_APP_ID
```

---

## 📊 Usage Tracking

Every chat request is recorded to `usage.db` (SQLite, auto-created). Token counts are estimated (÷4 char heuristic) and marked `estimated: true`.

```bash
# Stats for the last 7 days
curl "http://127.0.0.1:8787/usage/stats?period=7d"

# Last 20 requests with prompt preview
curl "http://127.0.0.1:8787/usage/history?limit=20"

# Daily breakdown
curl "http://127.0.0.1:8787/usage/daily?days=7"
```

| Endpoint | Params | Default |
|---|---|---|
| `/usage/stats` | `period`: `24h` \| `7d` \| `30d` \| `all` | `24h` |
| `/usage/history` | `limit` (max 500), `offset` | `50`, `0` |
| `/usage/daily` | `days` (max 365) | `30` |

> 💡 To store the DB elsewhere: `USAGE_DB=/path/to/usage.db` in `.env`.

---

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `TRAE_BASE_URL` | `https://coresg-normal.trae.ai` | Upstream API — `auth.py` reports the correct value for your region |
| `TRAE_IDE_TOKEN` | required | Trae auth token (JWT) |
| `TRAE_MACHINE_ID` | required | Machine ID |
| `TRAE_DEVICE_ID` | required | Device ID |
| `TRAE_APP_ID` | required | App ID |
| `BIND_HOST` | `127.0.0.1` | Bind address — do not change |
| `BIND_PORT` | `8787` | Port |
| `API_KEY` | _(empty)_ | Optional: require Bearer auth on all endpoints |
| `TRAE_EXCLUDE_MODELS` | `claude3.5,aws_sdk_claude37_sonnet` | Comma-separated model IDs to hide from `/v1/models` |
| `USAGE_DB` | `usage.db` | Path to usage tracking database |

---

## 🧪 Test with curl

```bash
# Health check
curl http://127.0.0.1:8787/health

# List models
curl http://127.0.0.1:8787/v1/models

# Chat (non-streaming)
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Hello in 5 words"}]}'

# Chat (streaming)
curl -N http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

---

## ⚠️ Known Limitations

- **Newer models can't be proxied.** GPT-5.x, Gemini-3, MiniMax, Kimi — these run through `POST /api/agent/v3/create_agent_task` with an application-layer encrypted body (ByteDance's "aha" transport, entropy ≈ 8.0). The request can't be replayed without reversing the encryption.
- **Claude models may fail.** `claude3.5` and `aws_sdk_claude37_sonnet` return error `4023` if your account or region doesn't have access.
- **The chat protocol is internal.** Built from reverse-engineering Trae's prompt-pipeline — a Trae update can break it. If chat stops working, check `trae_client.py` first.

---

## 🔁 Breakage Notice

When Trae updates:
1. Check `build_trae_payload()` and SSE parsing in `trae_client.py`
2. Check headers and log paths in `auth.py`
3. Re-run `python auth.py --write` to refresh the token

---

## 📄 License

MIT — see [LICENSE](LICENSE)
