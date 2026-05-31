import json
import time
import httpx
from config import TRAE_BASE_URL, TRAE_HEADERS


def build_trae_payload(messages: list, model: str, stream: bool, max_tokens: int | None = None) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


def trae_events(line: str) -> dict | None:
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return {"done": True}
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None

    choices = obj.get("choices", [])
    if not choices:
        return None

    delta = choices[0].get("delta", {})
    content = delta.get("content") or delta.get("reasoning_content") or ""
    finish_reason = choices[0].get("finish_reason")

    return {
        "id": obj.get("id", ""),
        "object": "chat.completion.chunk",
        "created": obj.get("created", int(time.time())),
        "model": obj.get("model", ""),
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
        "done": False,
    }


async def stream_completion(messages: list, model: str, max_tokens: int | None = None):
    payload = build_trae_payload(messages, model, stream=True, max_tokens=max_tokens)
    headers = {**TRAE_HEADERS, "Content-Type": "application/json", "Accept": "text/event-stream"}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{TRAE_BASE_URL}/api/ide/v1/chat/completion",
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                event = trae_events(line)
                if event is None:
                    continue
                if event.get("done"):
                    yield "[DONE]"
                    return
                yield f"data: {json.dumps(event)}\n\n"


async def non_stream_completion(messages: list, model: str, max_tokens: int | None = None) -> dict:
    payload = build_trae_payload(messages, model, stream=True, max_tokens=max_tokens)
    headers = {**TRAE_HEADERS, "Content-Type": "application/json", "Accept": "text/event-stream"}
    full_content = ""
    finish_reason = "stop"
    completion_id = ""
    created = int(time.time())
    used_model = model

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{TRAE_BASE_URL}/api/ide/v1/chat/completion",
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                event = trae_events(line)
                if event is None:
                    continue
                if event.get("done"):
                    break
                choices = event.get("choices", [])
                if choices:
                    full_content += choices[0].get("delta", {}).get("content", "")
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]
                if not completion_id:
                    completion_id = event.get("id", "")
                    created = event.get("created", created)
                    used_model = event.get("model", model)

    return {
        "id": completion_id or f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": created,
        "model": used_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": full_content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def list_models() -> list[dict]:
    headers = {**TRAE_HEADERS, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{TRAE_BASE_URL}/api/ide/v1/model_list",
            params={"type": "llm_raw_chat"},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    models = []
    for m in data.get("model_configs", []):
        name = m.get("name") or m.get("model_name") or m.get("id", "")
        if not name:
            continue
        models.append({
            "id": name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "trae",
        })
    return models

