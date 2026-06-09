# E2E Tests + Remove Vision Capability

**Date:** 2026-06-09
**Branch:** feat/toolcall-model-tags

## Context

Tool call support was added to TraePilot. We need end-to-end tests that exercise every model
against every capability it claims to support, using the real Trae API. Vision is also being
removed from the capability map since TraePilot does not forward image content.

## Part 1: Remove Vision Capability

### trae_client.py — _CAPABILITIES

Remove `"vision"` from all model entries:

| Model | New Capabilities |
|---|---|
| gemini-2.5-pro-preview-03-25 | tools, streaming, reasoning |
| gemini_2.5_flash | tools, streaming, reasoning |
| gpt-4.1-2025-04-14 | tools, streaming |
| gpt-4o | tools, streaming |
| deepseek-v3-0324 | tools, streaming |
| deepseek-v3 | tools, streaming |
| deepseek-r1 | tools, streaming, reasoning |

### dashboard.js — CAP_LABEL

Remove `vision: '👁 vision'` entry from the `CAP_LABEL` map in `renderModels()`.

### Tests

Update `test_get_capabilities_exact_match` to no longer expect `"vision"` in the result set.

## Part 2: E2E Test Suite

### File Structure

```
tests/
  e2e/
    __init__.py          # empty
    conftest.py          # e2e mark registration, async_client fixture
    test_models.py       # 4 parametrized test functions
```

### Architecture

At module import time in `test_models.py`, `asyncio.run()` fetches `/v1/models` once via an
in-process `httpx.AsyncClient` with `ASGITransport(app=app)`. The response is partitioned into
four lists used for `pytest.mark.parametrize`. If the API is unreachable (missing credentials,
network error), all lists are empty and every test is skipped via `pytest.skip`.

### conftest.py

- Registers `e2e` pytest mark
- Provides `async_client` as a **session-scoped** async fixture returning an
  `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`

### test_models.py

Four tests, each decorated with `@pytest.mark.e2e`:

#### test_basic_chat[model_id]
Parametrized over `_ALL_MODELS` (all 7).

- POST `/v1/chat/completions` `{"model": model_id, "messages": [{"role": "user", "content": "Reply with exactly the word: hello"}]}`
- Assert HTTP 200
- Assert `choices[0].message.content` is non-empty string

#### test_streaming[model_id]
Parametrized over `_STREAMING_MODELS` (all 7).

- POST with `stream: true`
- Collect all SSE lines until `[DONE]`
- Assert at least one `data:` chunk with non-empty `delta.content`
- Assert final chunk has a `finish_reason`
- Assert `[DONE]` was received

#### test_tool_call[model_id]
Parametrized over `_TOOL_MODELS` (all 7).

Tool definition used:
```json
{"type": "function", "function": {"name": "get_weather", "description": "Get weather for a city", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
```

- POST with `tools: [get_weather]` and `tool_choice: "required"`
- Assert HTTP 200
- Assert `choices[0].finish_reason == "tool_calls"`
- Assert `choices[0].message.tool_calls` is a non-empty list
- Assert `choices[0].message.tool_calls[0].function.name == "get_weather"`

#### test_reasoning[model_id]
Parametrized over `_REASONING_MODELS` (gemini-2.5-pro-preview-03-25, gemini_2.5_flash, deepseek-r1).

- POST `{"model": model_id, "messages": [{"role": "user", "content": "What is 17 * 23? Think step by step."}]}`
- Assert HTTP 200
- Assert response content contains `<think>`

### Graceful skip

```python
_SKIP_REASON = None
try:
    _ALL_MODELS = asyncio.run(_fetch_models())
except Exception as e:
    _ALL_MODELS = []
    _SKIP_REASON = f"Could not reach Trae API: {e}"
```

Each test calls `pytest.skip(_SKIP_REASON)` at the top if `_SKIP_REASON` is set.

### Running

```bash
pytest tests/e2e/ -m e2e -v
```

## Files to Modify / Create

- `trae_client.py` — remove vision from `_CAPABILITIES`
- `static/dashboard.js` — remove vision from `CAP_LABEL`
- `tests/test_trae_client.py` — update `test_get_capabilities_exact_match`
- `tests/e2e/__init__.py` — new (empty)
- `tests/e2e/conftest.py` — new
- `tests/e2e/test_models.py` — new
