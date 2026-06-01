import json
import time
import uuid
import httpx
from config import TRAE_BASE_URL, TRAE_HEADERS, EXCLUDE_MODELS

# Trae's chat-scene endpoint: a prompt-pipeline protocol that streams named SSE
# events (output / done / error), not OpenAI SSE. Request format derived from the
# (archived) trae2api project and verified against the live API.
CHAT_ENDPOINT = "/api/ide/v1/chat"


def _variables(last_input: str) -> str:
    """The stringified `variables` blob Trae's prompt pipeline expects."""
    try:
        version_code = int(TRAE_HEADERS.get("x-ide-version-code") or 0)
    except ValueError:
        version_code = 0
    return json.dumps({
        "language": "", "locale": "en-us", "input": last_input,
        "version_code": version_code, "is_inline_chat": False, "is_command": False,
        "raw_input": last_input, "problem": "", "current_filename": "",
        "is_select_code_before_chat": False, "last_select_time": 0,
        "last_turn_session": "", "hash_workspace": False, "hash_file": 0,
        "hash_code": 0, "use_filepath": True,
        "current_time": time.strftime("%Y%m%d %H:%M:%S"),
        "badge_clickable": True, "workspace_path": "/home/user/projects/traepilot",
        "brand": "Trae", "system_type": "Windows",
    })


def build_trae_payload(messages: list, model: str) -> dict:
    """Map OpenAI chat messages to Trae's /api/ide/v1/chat prompt-pipeline body."""
    def as_text(content) -> str:
        return content if isinstance(content, str) else str(content)

    last_input = as_text(messages[-1]["content"]) if messages else ""
    session_id = str(uuid.uuid4())

    history = []
    for m in messages[:-1]:
        history.append({
            "role": m["role"],
            "content": as_text(m["content"]),
            "status": "success",
            "locale": "en-us" if m["role"] == "assistant" else "",
            "session_id": session_id,
        })

    payload = {
        "user_input": last_input,
        "intent_name": "general_qa_intent",
        "variables": _variables(last_input),
        "context_resolvers": [
            {"resolver_id": "project-labels", "variables": "{\"labels\":\"\"}"},
            {"resolver_id": "terminal_context", "variables": "{\"terminal_context\":[]}"},
        ],
        "generate_suggested_questions": False,
        "chat_history": history,
        "session_id": session_id,
        "conversation_id": session_id,
        "current_turn": max(len(messages) - 1, 0),
        "valid_turns": list(range(len(history))),
        "multi_media": [],
        "model_name": model,
        "is_preset": True,
        "provider": "",
    }
    if history and history[-1]["role"] == "assistant":
        payload["last_llm_response_info"] = {
            "turn": len(history) - 1,
            "is_error": False,
            "response": history[-1]["content"],
        }
    return payload


async def _trae_chat_events(messages: list, model: str):
    """Yield (event, data) from Trae's chat SSE stream; raise RuntimeError on error."""
    payload = build_trae_payload(messages, model)
    headers = {**TRAE_HEADERS, "Content-Type": "application/json", "Accept": "*/*"}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{TRAE_BASE_URL}{CHAT_ENDPOINT}", json=payload, headers=headers
        ) as resp:
            resp.raise_for_status()
            event = ""
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event == "error":
                        raise RuntimeError(
                            data.get("message") or f"Trae error code {data.get('code')}"
                        )
                    yield event, data


def _delta(reasoning: str, response: str, think_open: list) -> str:
    """Build one content delta, wrapping reasoning_content in <think></think>."""
    out = ""
    if reasoning:
        out += ("<think>\n" + reasoning) if not think_open[0] else reasoning
        think_open[0] = True
    if response:
        out += ("\n</think>\n\n" + response) if think_open[0] else response
        think_open[0] = False
    return out


async def stream_completion(messages: list, model: str, max_tokens: int | None = None):
    think_open = [False]
    created = int(time.time())
    cid = f"chatcmpl-{created}"
    async for event, data in _trae_chat_events(messages, model):
        if event == "output":
            delta = _delta(data.get("reasoning_content") or "", data.get("response") or "", think_open)
            if delta:
                chunk = {
                    "id": cid, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        elif event == "done":
            chunk = {
                "id": cid, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": data.get("finish_reason") or "stop"}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "[DONE]"
            return


async def non_stream_completion(messages: list, model: str, max_tokens: int | None = None) -> dict:
    content, reasoning, finish_reason = "", "", "stop"
    async for event, data in _trae_chat_events(messages, model):
        if event == "output":
            content += data.get("response") or ""
            reasoning += data.get("reasoning_content") or ""
            if data.get("finish_reason"):
                finish_reason = data["finish_reason"]
        elif event == "done":
            if data.get("finish_reason"):
                finish_reason = data["finish_reason"]
    full = f"<think>\n{reasoning}\n</think>\n\n{content}" if reasoning else content
    created = int(time.time())
    return {
        "id": f"chatcmpl-{created}", "object": "chat.completion", "created": created,
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": full}, "finish_reason": finish_reason}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def list_models() -> list[dict]:
    headers = {**TRAE_HEADERS, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{TRAE_BASE_URL}/api/ide/v1/model_list",
            params={"type": "chat"},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    models = []
    for m in data.get("model_configs", []):
        name = m.get("name") or m.get("model_name") or m.get("id", "")
        if not name or name in EXCLUDE_MODELS:
            continue
        models.append({"id": name, "object": "model", "created": int(time.time()), "owned_by": "trae"})
    return models
