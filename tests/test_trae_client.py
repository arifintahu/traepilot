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
    assert set(caps) == {'tools', 'streaming', 'vision', 'reasoning'}

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
    assert set(gpt['capabilities']) == {'tools', 'streaming', 'vision'}
    unknown = next(m for m in models if m['id'] == 'unknown-model')
    assert unknown['capabilities'] == ['streaming']


# ── _convert_tool_messages ────────────────────────────────────────────────────

def test_convert_tool_role_to_user():
    from trae_client import _convert_tool_messages
    msgs = [{'role': 'tool', 'content': '72°F', 'tool_call_id': 'call_1'}]
    out = _convert_tool_messages(msgs)
    assert out[0]['role'] == 'user'
    assert 'call_1' in out[0]['content']
    assert '72°F' in out[0]['content']


def test_convert_assistant_tool_calls_to_text():
    from trae_client import _convert_tool_messages
    msgs = [{'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call_1', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city":"NY"}'}}
    ]}]
    out = _convert_tool_messages(msgs)
    assert out[0]['role'] == 'assistant'
    assert 'get_weather' in out[0]['content']


def test_convert_plain_messages_unchanged():
    from trae_client import _convert_tool_messages
    msgs = [{'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'hi'}]
    out = _convert_tool_messages(msgs)
    assert out == msgs


# ── _build_tools_system_prompt ────────────────────────────────────────────────

def test_build_tools_system_prompt_contains_function_name():
    from trae_client import _build_tools_system_prompt
    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {}}}]
    prompt = _build_tools_system_prompt(tools, 'auto')
    assert 'get_weather' in prompt
    assert 'tool_calls' in prompt


def test_build_tools_system_prompt_required_adds_must_call():
    from trae_client import _build_tools_system_prompt
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    prompt = _build_tools_system_prompt(tools, 'required')
    assert 'MUST' in prompt


# ── _parse_tool_call_response ─────────────────────────────────────────────────

def test_parse_tool_call_response_valid_json():
    from trae_client import _parse_tool_call_response
    text = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"NY\\"}"}}]}'
    calls = _parse_tool_call_response(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'get_weather'


def test_parse_tool_call_response_plain_text_returns_none():
    from trae_client import _parse_tool_call_response
    assert _parse_tool_call_response('The weather in NY is 72°F.') is None


def test_parse_tool_call_response_adds_missing_id():
    from trae_client import _parse_tool_call_response
    text = '{"tool_calls": [{"type": "function", "function": {"name": "fn", "arguments": "{}"}}]}'
    calls = _parse_tool_call_response(text)
    assert calls is not None
    assert calls[0]['id'].startswith('call_')


# ── _prepare_messages ─────────────────────────────────────────────────────────

def test_prepare_messages_injects_system_prompt():
    from trae_client import _prepare_messages
    msgs = [{'role': 'user', 'content': 'use a tool'}]
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    out = _prepare_messages(msgs, tools, 'auto')
    assert out[0]['role'] == 'system'
    assert 'fn' in out[0]['content']
    assert out[-1]['role'] == 'user'


def test_prepare_messages_no_tools_returns_unchanged():
    from trae_client import _prepare_messages
    msgs = [{'role': 'user', 'content': 'hello'}]
    out = _prepare_messages(msgs, None, None)
    assert out == msgs


def test_prepare_messages_merges_with_existing_system():
    from trae_client import _prepare_messages
    msgs = [{'role': 'system', 'content': 'Be helpful.'}, {'role': 'user', 'content': 'hi'}]
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    out = _prepare_messages(msgs, tools, 'auto')
    assert out[0]['role'] == 'system'
    assert 'Be helpful.' in out[0]['content']
    assert 'fn' in out[0]['content']


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
