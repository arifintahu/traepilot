import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_build_trae_payload_stream():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from trae_client import build_trae_payload
    payload = build_trae_payload([{'role': 'user', 'content': 'hi'}], 'gpt-4o', True, 100)
    assert payload['stream'] is True
    assert payload['model'] == 'gpt-4o'
    assert payload['max_tokens'] == 100


def test_build_trae_payload_no_max_tokens():
    from trae_client import build_trae_payload
    payload = build_trae_payload([{'role': 'user', 'content': 'hi'}], 'gpt-4o', False)
    assert 'max_tokens' not in payload


def test_trae_events_parses_chunk():
    from trae_client import trae_events
    chunk = json.dumps({
        'id': 'abc', 'created': 1000, 'model': 'gpt-4o',
        'choices': [{'delta': {'content': 'Hello'}, 'finish_reason': None}]
    })
    event = trae_events(f'data: {chunk}')
    assert event is not None
    assert event['choices'][0]['delta']['content'] == 'Hello'
    assert event['done'] is False


def test_trae_events_done():
    from trae_client import trae_events
    event = trae_events('data: [DONE]')
    assert event == {'done': True}


def test_trae_events_ignores_non_data():
    from trae_client import trae_events
    assert trae_events('') is None
    assert trae_events(': ping') is None
    assert trae_events('event: message') is None


def test_trae_events_empty_choices():
    from trae_client import trae_events
    chunk = json.dumps({'id': 'x', 'choices': []})
    assert trae_events(f'data: {chunk}') is None


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
