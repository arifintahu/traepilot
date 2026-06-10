import pytest
from pydantic import ValidationError


def test_message_accepts_tool_role_fields():
    from routes_openai import Message
    m = Message(role='tool', content='result text', tool_call_id='call_abc', name='get_weather')
    assert m.tool_call_id == 'call_abc'
    assert m.name == 'get_weather'


def test_message_content_optional_for_assistant_tool_call():
    from routes_openai import Message
    m = Message(role='assistant', content=None, tool_calls=[
        {'id': 'call_1', 'type': 'function', 'function': {'name': 'fn', 'arguments': '{}'}}
    ])
    assert m.content is None
    assert len(m.tool_calls) == 1


def test_chat_request_accepts_tools():
    from routes_openai import ChatCompletionRequest, Message
    req = ChatCompletionRequest(
        model='gpt-4o',
        messages=[Message(role='user', content='hello')],
        tools=[{'type': 'function', 'function': {'name': 'fn', 'description': 'does stuff', 'parameters': {}}}],
        tool_choice='required',
    )
    assert req.tool_choice == 'required'
    assert len(req.tools) == 1


def test_chat_request_tools_default_none():
    from routes_openai import ChatCompletionRequest, Message
    req = ChatCompletionRequest(model='gpt-4o', messages=[Message(role='user', content='hi')])
    assert req.tools is None
    assert req.tool_choice is None
