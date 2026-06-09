"""End-to-end tests: every model × every capability it claims to support.

Run with:  pytest tests/e2e/ -m e2e -v
Skip when Trae API unreachable or credentials missing.
"""
import asyncio
import json
import pytest
import httpx
from httpx import ASGITransport
from main import app

# ---------------------------------------------------------------------------
# One-time model discovery at import time
# ---------------------------------------------------------------------------

async def _fetch_models() -> list[dict]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/models")
        resp.raise_for_status()
        return resp.json()["data"]


_SKIP_REASON: str | None = None
_ALL_MODELS: list[str] = []
_STREAMING_MODELS: list[str] = []
_TOOL_MODELS: list[str] = []
_REASONING_MODELS: list[str] = []

try:
    _discovered = asyncio.run(_fetch_models())
    for _m in _discovered:
        mid = _m["id"]
        caps = set(_m.get("capabilities", []))
        _ALL_MODELS.append(mid)
        if "streaming" in caps:
            _STREAMING_MODELS.append(mid)
        if "tools" in caps:
            _TOOL_MODELS.append(mid)
        if "reasoning" in caps:
            _REASONING_MODELS.append(mid)
except Exception as _exc:
    _SKIP_REASON = f"Could not reach Trae API: {_exc}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skip_if_unavailable():
    if _SKIP_REASON:
        pytest.skip(_SKIP_REASON)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.parametrize("model_id", _ALL_MODELS or ["__placeholder__"])
async def test_basic_chat(async_client: httpx.AsyncClient, model_id: str):
    """Basic non-streaming chat returns a non-empty response."""
    _skip_if_unavailable()
    if model_id == "__placeholder__":
        pytest.skip("No models discovered")

    resp = await async_client.post("/v1/chat/completions", json={
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly the word: hello"}],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip(), \
        f"Expected non-empty content, got: {content!r}"


@pytest.mark.e2e
@pytest.mark.parametrize("model_id", _STREAMING_MODELS or ["__placeholder__"])
async def test_streaming(async_client: httpx.AsyncClient, model_id: str):
    """Streaming returns valid SSE chunks with content and a finish_reason."""
    _skip_if_unavailable()
    if model_id == "__placeholder__":
        pytest.skip("No streaming models discovered")

    async with async_client.stream("POST", "/v1/chat/completions", json={
        "model": model_id,
        "stream": True,
        "messages": [{"role": "user", "content": "Say hi in one word."}],
    }) as resp:
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        chunks = []
        bad_lines: list = []
        got_done = False
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line == "data: [DONE]":
                got_done = True
                break
            if line.startswith("data: "):
                try:
                    chunks.append(json.loads(line[6:]))
                except json.JSONDecodeError as _json_err:
                    bad_lines.append((line, str(_json_err)))

    assert not bad_lines, f"Malformed SSE data lines: {bad_lines}"
    assert got_done, "SSE stream did not end with [DONE]"
    content_chunks = [
        c for c in chunks
        if c.get("choices", [{}])[0].get("delta", {}).get("content")
    ]
    assert content_chunks, "No content delta found in stream chunks"

    finish_chunks = [
        c for c in chunks
        if c.get("choices", [{}])[0].get("finish_reason")
    ]
    assert finish_chunks, "No chunk with finish_reason found"


@pytest.mark.e2e
@pytest.mark.parametrize("model_id", _TOOL_MODELS or ["__placeholder__"])
async def test_tool_call(async_client: httpx.AsyncClient, model_id: str):
    """Tool-capable models call get_weather when tool_choice is required."""
    _skip_if_unavailable()
    if model_id == "__placeholder__":
        pytest.skip("No tool-capable models discovered")

    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }]

    resp = await async_client.post("/v1/chat/completions", json={
        "model": model_id,
        "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
        "tools": tools,
        "tool_choice": "required",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    choice = body["choices"][0]
    assert choice["finish_reason"] == "tool_calls", \
        f"Expected finish_reason='tool_calls', got {choice['finish_reason']!r}"
    tool_calls = choice["message"].get("tool_calls")
    assert tool_calls and len(tool_calls) > 0, "Expected non-empty tool_calls list"
    assert tool_calls[0]["function"]["name"] == "get_weather", \
        f"Expected function name 'get_weather', got {tool_calls[0]['function']['name']!r}"
    try:
        args = json.loads(tool_calls[0]["function"]["arguments"])
    except (json.JSONDecodeError, TypeError) as _e:
        pytest.fail(f"tool_calls[0].function.arguments is not valid JSON: {_e!r}")
    assert "city" in args, f"Expected 'city' in arguments, got {args!r}"


@pytest.mark.e2e
@pytest.mark.parametrize("model_id", _REASONING_MODELS or ["__placeholder__"])
async def test_reasoning(async_client: httpx.AsyncClient, model_id: str):
    """Reasoning models return the correct answer to a multi-step arithmetic problem."""
    _skip_if_unavailable()
    if model_id == "__placeholder__":
        pytest.skip("No reasoning models discovered")

    resp = await async_client.post("/v1/chat/completions", json={
        "model": model_id,
        "messages": [{"role": "user", "content": (
            "A binary search runs on a sorted array of 1024 elements. "
            "How many comparisons are needed in the worst case? Show each step."
        )}],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    content = body["choices"][0]["message"]["content"] or ""
    # log2(1024) = 10; any reasoning model should arrive at this answer
    assert "10" in content, \
        f"Expected '10' (log2(1024)) in reasoning model output, got: {content[:100]!r}...{content[-100:]!r}"
