import json
import logging
import re
import uuid

logger = logging.getLogger("traepilot")

_TOOL_CALL_START = re.compile(r'\{\s*"tool_calls"\s*:')
_FENCE_BEFORE = re.compile(r"(?:```(?:json)?|`)\s*$")
_FENCE_AFTER = re.compile(r"^\s*(?:```(?:json)?|`)")


def _convert_tool_messages(messages: list) -> list:
    """Convert tool-role and tool_calls messages to plain text for Trae's format."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            tid = m.get("tool_call_id", "")
            out.append({"role": "user", "content": f"[Tool result for {tid}: {m.get('content', '')}]"})
        elif role == "assistant" and m.get("tool_calls"):
            text_preamble = m.get("content") or ""
            parts = [text_preamble] if text_preamble else []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                parts.append(f"[Called: {fn.get('name', '')}({fn.get('arguments', '')})]")
            out.append({"role": "assistant", "content": "\n".join(parts)})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def _build_tools_system_prompt(tools: list, tool_choice) -> str:
    """Build a system prompt that instructs the model to respond with a JSON tool call."""
    tool_defs = json.dumps(tools, indent=2)
    prompt = (
        "You have access to the following functions. "
        "When you want to call a function, respond ONLY with a JSON object — no other text:\n"
        '{"tool_calls": [{"id": "call_<id>", "type": "function", '
        '"function": {"name": "<name>", "arguments": "<json-escaped-args>"}}]}\n\n'
        f"Available functions:\n{tool_defs}"
    )
    if tool_choice == "required":
        prompt += "\n\nYou MUST call a function. Do not reply with plain text."
    return prompt


def _validate_tool_calls(obj) -> list | None:
    """Return the normalized tool_calls list from a parsed object, else None."""
    calls = obj.get("tool_calls") if isinstance(obj, dict) else None
    if not isinstance(calls, list) or not calls:
        return None
    for call in calls:
        if not isinstance(call, dict) or "function" not in call:
            return None
        if "id" not in call:
            call["id"] = f"call_{uuid.uuid4().hex[:8]}"
        call.setdefault("type", "function")
    return calls


def _find_balanced_json(text: str, start: int) -> tuple[int, list, bool]:
    """Scan a JSON value from text[start] == '{', tracking strings and escapes.
    Returns (end_index_exclusive, open_stack, in_string); end is -1 if the
    text runs out before the object balances (truncated output)."""
    stack: list[str] = []
    in_str = esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "{[":
            stack.append(c)
        elif c in "}]":
            if stack:
                stack.pop()
            if not stack:
                return i + 1, stack, False
    return -1, stack, in_str


def _repair_json(fragment: str, open_stack: list, in_string: bool) -> str:
    """Close an unterminated string, drop a trailing comma, and append the
    missing closers so a truncated tool-call object becomes parseable."""
    repaired = fragment
    if in_string:
        repaired += '"'
    repaired = repaired.rstrip()
    if repaired.endswith(","):
        repaired = repaired[:-1]
    for opener in reversed(open_stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def _extract_tool_calls(text: str) -> tuple[str, list | None]:
    """Extract tool-call JSON from anywhere in model output (after prose,
    inside backticks/fences, or truncated). Returns (remaining_prose, calls);
    calls is None and prose is the original text when nothing usable is found."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = "\n".join(lines[1:-1]).strip() if len(lines) > 2 else ""
        if inner:
            stripped = inner
    try:
        calls = _validate_tool_calls(json.loads(stripped))
        if calls:
            return "", calls
    except (json.JSONDecodeError, ValueError):
        pass

    for m in _TOOL_CALL_START.finditer(text):
        start = m.start()
        end, stack, in_str = _find_balanced_json(text, start)
        if end == -1:
            candidate = _repair_json(text[start:], stack, in_str)
            end = len(text)
        else:
            candidate = text[start:end]
        try:
            calls = _validate_tool_calls(json.loads(candidate))
        except (json.JSONDecodeError, ValueError):
            calls = None
        if calls:
            before = _FENCE_BEFORE.sub("", text[:start]).rstrip()
            after = _FENCE_AFTER.sub("", text[end:]).strip()
            prose = (before + "\n" + after).strip() if after else before.strip()
            return prose, calls
        logger.warning(
            "tool_calls-like JSON could not be parsed or repaired; "
            "passing content through unchanged: %r", text[start:end][:500],
        )
    return text, None


def _parse_tool_call_response(text: str) -> list | None:
    """Return parsed tool_calls found in text, else None (prose discarded)."""
    return _extract_tool_calls(text)[1]


def _prepare_messages(messages: list, tools: list | None, tool_choice) -> list:
    """Inject tool system prompt and convert tool messages when tools are provided."""
    if not tools:
        return messages
    converted = _convert_tool_messages(messages)
    sys_content = _build_tools_system_prompt(tools, tool_choice)
    if converted and converted[0]["role"] == "system":
        converted[0] = {"role": "system", "content": sys_content + "\n\n" + converted[0]["content"]}
        return converted
    return [{"role": "system", "content": sys_content}] + converted
