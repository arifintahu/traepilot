import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── build_trae_payload ────────────────────────────────────────────────────────
# Current signature: build_trae_payload(messages: list, model: str) -> dict
#
# The old tests called it with (messages, model, stream, max_tokens). Those
# args were removed when the upstream protocol switched from OpenAI SSE to
# Trae's named-event prompt-pipeline format. stream/max_tokens are no longer
# part of the payload; the model is stored as model_name (Trae's key).

def test_build_trae_payload_sets_model_name():
    from trae_client import build_trae_payload
    payload = build_trae_payload([{'role': 'user', 'content': 'hi'}], 'gpt-4o')
    assert payload['model_name'] == 'gpt-4o'


def test_build_trae_payload_sets_user_input_from_last_message():
    from trae_client import build_trae_payload
    payload = build_trae_payload([{'role': 'user', 'content': 'hello world'}], 'gpt-4o')
    assert payload['user_input'] == 'hello world'


def test_build_trae_payload_puts_all_but_last_in_history():
    from trae_client import build_trae_payload
    messages = [
        {'role': 'user',      'content': 'first'},
        {'role': 'assistant', 'content': 'reply'},
        {'role': 'user',      'content': 'last'},
    ]
    payload = build_trae_payload(messages, 'gpt-4o')
    assert payload['user_input'] == 'last'
    assert len(payload['chat_history']) == 2
    assert payload['current_turn'] == 2


def test_build_trae_payload_intent_name():
    from trae_client import build_trae_payload
    payload = build_trae_payload([{'role': 'user', 'content': 'hi'}], 'gpt-4o')
    assert payload['intent_name'] == 'general_qa_intent'


# ── _delta ────────────────────────────────────────────────────────────────────
# trae_events() no longer exists. _delta() is the current equivalent: it merges
# reasoning and response chunks, wrapping reasoning in <think></think> tags.

def test_delta_plain_response_no_reasoning():
    from trae_client import _delta
    think_open = [False]
    out = _delta('', 'hello', think_open)
    assert out == 'hello'
    assert think_open[0] is False


def test_delta_opens_think_tag_on_first_reasoning_chunk():
    from trae_client import _delta
    think_open = [False]
    out = _delta('some reasoning', '', think_open)
    assert out == '<think>\nsome reasoning'
    assert think_open[0] is True


def test_delta_continues_reasoning_inside_open_think_tag():
    from trae_client import _delta
    think_open = [True]
    out = _delta('more reasoning', '', think_open)
    assert out == 'more reasoning'
    assert think_open[0] is True


def test_delta_closes_think_tag_on_first_response_chunk():
    from trae_client import _delta
    think_open = [True]
    out = _delta('', 'response text', think_open)
    assert out == '\n</think>\n\nresponse text'
    assert think_open[0] is False


def test_delta_empty_inputs_produce_empty_output():
    from trae_client import _delta
    think_open = [False]
    assert _delta('', '', think_open) == ''


# ── list_models ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_models_parsing():
    from trae_client import list_models
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        'model_configs': [
            {'model_name': 'claude-3-5-sonnet'},
            {'model_name': 'gpt-4o'},
        ]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    with patch('trae_client.httpx.AsyncClient', return_value=mock_client):
        models = await list_models()
    assert len(models) == 2
    assert models[0]['id'] == 'claude-3-5-sonnet'
    assert models[1]['id'] == 'gpt-4o'
    assert all(m['object'] == 'model' for m in models)


# ── _get_capabilities ─────────────────────────────────────────────────────────

def test_get_capabilities_exact_match():
    from trae_client import _get_capabilities
    caps = _get_capabilities('gemini-2.5-pro-preview-03-25')
    assert set(caps) == {'tools', 'streaming', 'reasoning'}

def test_get_capabilities_case_insensitive():
    from trae_client import _get_capabilities
    assert 'tools' in _get_capabilities('DeepSeek-R1')
    assert 'reasoning' in _get_capabilities('deepseek-r1')

def test_get_capabilities_default_streaming():
    from trae_client import _get_capabilities
    caps = _get_capabilities('some-unknown-model')
    assert caps == ['streaming']

def test_get_capabilities_deepseek_v3():
    from trae_client import _get_capabilities
    caps = _get_capabilities('deepseek-V3')
    assert 'tools' in caps
    assert 'reasoning' not in caps


@pytest.mark.asyncio
async def test_list_models_includes_capabilities():
    from trae_client import list_models
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        'model_configs': [{'model_name': 'gpt-4o'}, {'model_name': 'unknown-model'}]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    with patch('trae_client.httpx.AsyncClient', return_value=mock_client):
        models = await list_models()
    gpt = next(m for m in models if m['id'] == 'gpt-4o')
    assert set(gpt['capabilities']) == {'tools', 'streaming'}
    unknown = next(m for m in models if m['id'] == 'unknown-model')
    assert unknown['capabilities'] == ['streaming']


# ── non_stream_completion with tools ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_stream_completion_returns_tool_calls_when_detected():
    from trae_client import non_stream_completion
    tool_call_json = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"NY\\"}"}}]}'

    async def fake_events(messages, model):
        yield 'output', {'response': tool_call_json, 'reasoning_content': ''}
        yield 'done', {'finish_reason': 'stop'}

    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {}}}]
    with patch('trae_client._trae_chat_events', fake_events):
        result = await non_stream_completion([{'role': 'user', 'content': 'weather?'}], 'gpt-4o', tools=tools)
    choice = result['choices'][0]
    assert choice['finish_reason'] == 'tool_calls'
    assert choice['message']['tool_calls'][0]['function']['name'] == 'get_weather'
    assert choice['message']['content'] is None


@pytest.mark.asyncio
async def test_non_stream_completion_plain_text_unchanged():
    from trae_client import non_stream_completion

    async def fake_events(messages, model):
        yield 'output', {'response': 'The weather is sunny.', 'reasoning_content': ''}
        yield 'done', {'finish_reason': 'stop'}

    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {}}}]
    with patch('trae_client._trae_chat_events', fake_events):
        result = await non_stream_completion([{'role': 'user', 'content': 'weather?'}], 'gpt-4o', tools=tools)
    choice = result['choices'][0]
    assert choice['finish_reason'] == 'stop'
    assert 'sunny' in choice['message']['content']


# ── stream_completion with tools ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_completion_emits_tool_call_chunk():
    from trae_client import stream_completion
    tool_call_json = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"NY\\"}"}}]}'

    async def fake_events(messages, model):
        yield 'output', {'response': tool_call_json, 'reasoning_content': ''}
        yield 'done', {'finish_reason': 'stop'}

    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {}}}]
    chunks = []
    with patch('trae_client._trae_chat_events', fake_events):
        async for chunk in stream_completion([{'role': 'user', 'content': 'weather?'}], 'gpt-4o', tools=tools):
            chunks.append(chunk)

    assert chunks[-1] == '[DONE]'
    data_chunks = [c for c in chunks if c.startswith('data:') and '[DONE]' not in c]
    assert len(data_chunks) == 1
    payload = json.loads(data_chunks[0][6:])
    choice = payload['choices'][0]
    assert choice['finish_reason'] == 'tool_calls'
    assert choice['delta']['tool_calls'][0]['function']['name'] == 'get_weather'
    assert choice['delta']['tool_calls'][0].get('index') == 0


@pytest.mark.asyncio
async def test_non_stream_completion_extracts_tool_call_after_prose():
    from trae_client import non_stream_completion
    text = (
        'I will search for pools now.\n'
        '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_pools", "arguments": "{\\"query\\":\\"BILLY\\"}"}}]}'
    )

    async def fake_events(messages, model):
        yield 'output', {'response': text, 'reasoning_content': ''}
        yield 'done', {'finish_reason': 'stop'}

    tools = [{'type': 'function', 'function': {'name': 'search_pools', 'parameters': {}}}]
    with patch('trae_client._trae_chat_events', fake_events):
        result = await non_stream_completion([{'role': 'user', 'content': 'go'}], 'gpt-4o', tools=tools)
    choice = result['choices'][0]
    assert choice['finish_reason'] == 'tool_calls'
    assert choice['message']['tool_calls'][0]['function']['name'] == 'search_pools'
    assert choice['message']['content'] == 'I will search for pools now.'


@pytest.mark.asyncio
async def test_stream_completion_extracts_tool_call_split_across_chunks():
    # Prose + tool-call JSON, with the JSON split across two SSE chunks
    from trae_client import stream_completion
    part1 = 'I will search for pools now.\n{"tool_calls": [{"id": "call_1", '
    part2 = '"type": "function", "function": {"name": "search_pools", "arguments": "{}"}}]}'

    async def fake_events(messages, model):
        yield 'output', {'response': part1, 'reasoning_content': ''}
        yield 'output', {'response': part2, 'reasoning_content': ''}
        yield 'done', {'finish_reason': 'stop'}

    tools = [{'type': 'function', 'function': {'name': 'search_pools', 'parameters': {}}}]
    chunks = []
    with patch('trae_client._trae_chat_events', fake_events):
        async for chunk in stream_completion([{'role': 'user', 'content': 'go'}], 'gpt-4o', tools=tools):
            chunks.append(chunk)

    data_chunks = [c for c in chunks if c.startswith('data:') and '[DONE]' not in c]
    assert len(data_chunks) == 1
    choice = json.loads(data_chunks[0][6:])['choices'][0]
    assert choice['finish_reason'] == 'tool_calls'
    assert choice['delta']['tool_calls'][0]['function']['name'] == 'search_pools'
    assert choice['delta']['content'] == 'I will search for pools now.'
