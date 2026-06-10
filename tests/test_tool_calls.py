import json
import pytest


def test_convert_tool_role_to_user():
    from tool_calls import _convert_tool_messages
    msgs = [{'role': 'tool', 'content': '72°F', 'tool_call_id': 'call_1'}]
    out = _convert_tool_messages(msgs)
    assert out[0]['role'] == 'user'
    assert 'call_1' in out[0]['content']
    assert '72°F' in out[0]['content']


def test_convert_assistant_tool_calls_to_text():
    from tool_calls import _convert_tool_messages
    msgs = [{'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call_1', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city":"NY"}'}}
    ]}]
    out = _convert_tool_messages(msgs)
    assert out[0]['role'] == 'assistant'
    assert 'get_weather' in out[0]['content']


def test_convert_assistant_preserves_text_content_with_tool_calls():
    from tool_calls import _convert_tool_messages
    msgs = [{'role': 'assistant', 'content': 'Sure, let me look that up.', 'tool_calls': [
        {'id': 'call_1', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{}'}}
    ]}]
    out = _convert_tool_messages(msgs)
    assert 'Sure, let me look that up.' in out[0]['content']
    assert 'get_weather' in out[0]['content']


def test_convert_plain_messages_unchanged():
    from tool_calls import _convert_tool_messages
    msgs = [{'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'hi'}]
    out = _convert_tool_messages(msgs)
    assert out == msgs


def test_build_tools_system_prompt_contains_function_name():
    from tool_calls import _build_tools_system_prompt
    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {}}}]
    prompt = _build_tools_system_prompt(tools, 'auto')
    assert 'get_weather' in prompt
    assert 'tool_calls' in prompt


def test_build_tools_system_prompt_required_adds_must_call():
    from tool_calls import _build_tools_system_prompt
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    prompt = _build_tools_system_prompt(tools, 'required')
    assert 'MUST' in prompt


def test_parse_tool_call_response_valid_json():
    from tool_calls import _parse_tool_call_response
    text = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"NY\\"}"}}]}'
    calls = _parse_tool_call_response(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'get_weather'


def test_parse_tool_call_response_plain_text_returns_none():
    from tool_calls import _parse_tool_call_response
    assert _parse_tool_call_response('The weather in NY is 72°F.') is None


def test_parse_tool_call_response_adds_missing_id():
    from tool_calls import _parse_tool_call_response
    text = '{"tool_calls": [{"type": "function", "function": {"name": "fn", "arguments": "{}"}}]}'
    calls = _parse_tool_call_response(text)
    assert calls is not None
    assert calls[0]['id'].startswith('call_')


def test_parse_tool_call_response_strips_markdown_fences():
    from tool_calls import _parse_tool_call_response
    text = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"Paris\\"}"}}]}\n```'
    calls = _parse_tool_call_response(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'get_weather'


def test_parse_tool_call_response_strips_plain_fences():
    from tool_calls import _parse_tool_call_response
    text = '```\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "fn", "arguments": "{}"}}]}\n```'
    calls = _parse_tool_call_response(text)
    assert calls is not None


def test_extract_prose_then_truncated_json_at_end():
    from tool_calls import _extract_tool_calls
    text = (
        "I will proceed with evaluating the dominant BILLY token. My next step is "
        "to find the associated DLMM pool. I will search for pools using its mint "
        "address to be precise.\n"
        '{"tool_calls": [{"id": "call_66542111", "type": "function", "function": '
        '{"name": "search_pools", "arguments": "{\\"query\\": '
        '\\"3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump\\"}"}}'
    )
    prose, calls = _extract_tool_calls(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'search_pools'
    args = json.loads(calls[0]['function']['arguments'])
    assert args['query'] == '3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump'
    assert 'I will proceed' in prose
    assert 'tool_calls' not in prose


def test_extract_unrepairable_json_logs_warning(caplog):
    import logging
    from tool_calls import _extract_tool_calls
    text = (
        "...I'll start by fetching the top candidates again."
        '{"tool_calls": [{"id": "call_4y6w447h244444444444444444444444444'
    )
    with caplog.at_level(logging.WARNING, logger='traepilot'):
        prose, calls = _extract_tool_calls(text)
    assert calls is None
    assert prose == text
    assert 'tool_calls' in caplog.text


def test_extract_backtick_wrapped_json_after_prose():
    from tool_calls import _extract_tool_calls
    text = (
        'First, I need to get the top candidates. '
        '`{"tool_calls": [{"id": "call_4542345454", "type": "function", '
        '"function": {"name": "get_top_candidates", "arguments": "{}"}}]}`'
    )
    prose, calls = _extract_tool_calls(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'get_top_candidates'
    assert prose == 'First, I need to get the top candidates.'


def test_extract_fenced_json_after_prose():
    from tool_calls import _extract_tool_calls
    text = (
        'Let me call the tool.\n```json\n'
        '{"tool_calls": [{"id": "call_1", "function": {"name": "fn", "arguments": "{}"}}]}\n```'
    )
    prose, calls = _extract_tool_calls(text)
    assert calls is not None
    assert calls[0]['function']['name'] == 'fn'
    assert prose == 'Let me call the tool.'


def test_extract_pure_prose_unchanged(caplog):
    import logging
    from tool_calls import _extract_tool_calls
    text = 'The weather in NY is 72°F. No tools needed.'
    with caplog.at_level(logging.WARNING, logger='traepilot'):
        prose, calls = _extract_tool_calls(text)
    assert calls is None
    assert prose == text
    assert caplog.text == ''


def test_extract_pure_tool_call_json_happy_path():
    from tool_calls import _extract_tool_calls
    text = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{\\"city\\":\\"NY\\"}"}}]}'
    prose, calls = _extract_tool_calls(text)
    assert prose == ''
    assert calls is not None
    assert calls[0]['function']['name'] == 'get_weather'


def test_prepare_messages_injects_system_prompt():
    from tool_calls import _prepare_messages
    msgs = [{'role': 'user', 'content': 'use a tool'}]
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    out = _prepare_messages(msgs, tools, 'auto')
    assert out[0]['role'] == 'system'
    assert 'fn' in out[0]['content']
    assert out[-1]['role'] == 'user'


def test_prepare_messages_no_tools_returns_unchanged():
    from tool_calls import _prepare_messages
    msgs = [{'role': 'user', 'content': 'hello'}]
    out = _prepare_messages(msgs, None, None)
    assert out == msgs


def test_prepare_messages_merges_with_existing_system():
    from tool_calls import _prepare_messages
    msgs = [{'role': 'system', 'content': 'Be helpful.'}, {'role': 'user', 'content': 'hi'}]
    tools = [{'type': 'function', 'function': {'name': 'fn', 'parameters': {}}}]
    out = _prepare_messages(msgs, tools, 'auto')
    assert out[0]['role'] == 'system'
    assert 'Be helpful.' in out[0]['content']
    assert 'fn' in out[0]['content']
