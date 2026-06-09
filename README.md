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
| ❌ No tool/function calling support | ✅ OpenAI-style tool calls (emulated) |
| ❌ No usage visibility | ✅ Local SQLite usage tracking + web dashboard |

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

| Model ID | Capabilities | Notes |
|---|---|---|
| `deepseek-V3` | tools · streaming | Recommended default |
| `deepseek-V3-0324` | tools · streaming | |
| `deepseek-R1` | tools · streaming · reasoning | Thinking-class model |
| `gpt-4o` | tools · streaming | |
| `gpt-4.1-2025-04-14` | tools · streaming | |
| `gemini-2.5-pro-preview-03-25` | tools · streaming · reasoning | Coding questions only via Trae |
| `gemini_2.5_flash` | tools · streaming · reasoning | |

> ℹ️ **Newer models** (GPT-5.x, Gemini-3, MiniMax, Kimi…) shown in Trae IDE cannot be proxied — their requests are encrypted at the application layer via ByteDance's "aha" transport. `/v1/models` lists only what's actually reachable.

> ℹ️ **Claude models** (`claude3.5`, `aws_sdk_claude37_sonnet`) are excluded by default — they return error `4023` unless your account/region has specific access. Re-enable by editing `TRAE_EXCLUDE_MODELS` in `.env`.

The `capabilities` field is returned on every model object in `/v1/models`, and each model card in the dashboard shows the same chips.

---

## 🔧 Tool Calls (Function Calling)

TraePilot emulates OpenAI-style tool calls for all models — Trae's API has no native function calling, so the proxy handles it transparently:

1. Tool definitions are injected into the request as a system prompt
2. The model is instructed to respond with a JSON `tool_calls` object
3. The proxy parses the response and returns it in the standard OpenAI format

**Usage — identical to the OpenAI API:**

```bash
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-V3",
    "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }],
    "tool_choice": "required"
  }'
```

Response follows the OpenAI format:
```json
{
  "choices": [{
    "finish_reason": "tool_calls",
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\": \"Paris\"}"
        }
      }]
    }
  }]
}
```

**Supported `tool_choice` values:** `"auto"`, `"required"`, `{"type": "function", "function": {"name": "..."}}`

**Multi-turn tool use** (passing tool results back) is also supported — use `role: "tool"` messages as normal.

> ⚠️ Tool calls are emulated. The model may occasionally respond with prose instead of a JSON call, especially with `tool_choice: "auto"`. Use `tool_choice: "required"` for deterministic behavior.

---

## 🖥️ Dashboard

Open the built-in dashboard in any browser while the proxy is running:

```
http://127.0.0.1:8787/dashboard
```

Five sections via the sidebar:

| Section | What it shows |
|---|---|
| **Usage** | Stat cards (requests, tokens) with sparklines, 7-day bar chart with hover tooltip, per-model breakdown table. Period tabs: 24h / 7d / 30d / All. |
| **History** | Full request log — searchable by prompt/model, filterable by status (All / OK / Errors), model dropdown filter, paginated. |
| **Models** | Live model list from Trae, grouped by provider (Gemini / OpenAI / DeepSeek) with color-coded avatar cards. Each card shows capability chips (⚙ tools · ⚡ stream · 🧠 reasoning). Copy model ID to clipboard. |
| **Test Chat** | Send `"Hello! Are you working?"` to any model you select. Shows the raw response, model, and latency. |
| **Config** | All env vars grouped into Connection / Device / IDE. Sensitive values (`API_KEY`, `TRAE_IDE_TOKEN`, `TRAE_MACHINE_ID`, `TRAE_DEVICE_ID`) are masked server-side — the real value is never sent to the browser. |

> 💡 If `API_KEY` is set in `.env`, the dashboard shows a key prompt on load and stores it in `sessionStorage` for the tab's lifetime.

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

> 💡 The [dashboard](#️-dashboard) shows this data visually — **Usage** for stat cards, bar chart, and model breakdown; **History** for the full searchable request log.

Or query the JSON API directly:

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

## 🗺️ API Reference

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/v1/models` | GET | optional | List available models with capability tags |
| `/v1/chat/completions` | POST | optional | Chat — streaming, non-streaming, and tool calls |
| `/usage/stats` | GET | optional | Aggregate token/request counts |
| `/usage/history` | GET | optional | Paginated request log |
| `/usage/daily` | GET | optional | Daily rollup |
| `/config` | GET | optional | All env config (sensitive fields masked) |
| `/dashboard` | GET | — | Web dashboard (HTML) |
| `/health` | GET | — | `{"status":"ok"}` |

"Optional" auth means the endpoint is open unless `API_KEY` is set in `.env`.

---

## 🧪 Test with curl

```bash
# Health check
curl http://127.0.0.1:8787/health

# List models (includes capabilities field)
curl http://127.0.0.1:8787/v1/models

# Chat (non-streaming)
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Hello in 5 words"}]}'

# Chat (streaming)
curl -N http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'

# Tool call
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-V3","messages":[{"role":"user","content":"Weather in Tokyo?"}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"tool_choice":"required"}'
```

---

## 🧪 Running Tests

```bash
# Unit tests (fast, no network)
pytest tests/ --ignore=tests/e2e -v

# E2E tests — hits the real Trae API (requires valid .env credentials)
pytest tests/e2e/ -m e2e -v
```

The e2e suite tests every model against every capability it claims to support: basic chat, streaming, tool calls, and reasoning. Tests skip automatically if credentials are missing or the API is unreachable.

---

## ⚠️ Known Limitations

- **Tool calls are emulated.** Trae's API has no native function calling. The proxy injects tool definitions as a system prompt and parses the model's JSON response. Works reliably with `tool_choice: "required"`; less deterministic with `"auto"`.
- **No image input.** Trae's endpoint does not forward image content from messages — multimodal requests are not supported.
- **Newer models can't be proxied.** GPT-5.x, Gemini-3, MiniMax, Kimi — these run through `POST /api/agent/v3/create_agent_task` with an application-layer encrypted body (ByteDance's "aha" transport, entropy ≈ 8.0). The request can't be replayed without reversing the encryption.
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
