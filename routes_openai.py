import json
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from deps import require_bearer
from trae_client import list_models, non_stream_completion, stream_completion
from usage import record_usage

router = APIRouter()


class Message(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False
    max_tokens: Optional[int] = None
    tools: Optional[list] = None
    tool_choice: Optional[str | dict] = None


@router.get("/v1/models")
async def get_models():
    try:
        models = await list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"object": "list", "data": models}


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, _: None = Depends(require_bearer)):
    messages = [m.model_dump(exclude_none=True) for m in req.messages]

    if req.stream:
        async def event_stream():
            accumulated = []
            status = "ok"
            error_detail = None
            finish_reason = None
            start_time = time.perf_counter()
            try:
                async for chunk in stream_completion(
                    messages, req.model, req.max_tokens,
                    tools=req.tools, tool_choice=req.tool_choice,
                ):
                    if chunk == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    yield chunk
                    try:
                        parsed = json.loads(chunk[6:])
                        choice = parsed["choices"][0]
                        delta = choice.get("delta", {})
                        text = delta.get("content") or ""
                        if text:
                            accumulated.append(text)
                        fr = choice.get("finish_reason")
                        if fr:
                            finish_reason = fr
                    except Exception:
                        pass
                else:
                    status = "error"
            except Exception as e:
                status = "error"
                error_detail = str(e)
                err = {"error": {"message": error_detail, "type": "upstream_error"}}
                yield f"data: {json.dumps(err)}\n\n"
            finally:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                await record_usage(
                    req.model, messages, "".join(accumulated), status, True,
                    duration_ms=duration_ms, error_detail=error_detail,
                    finish_reason=finish_reason,
                )
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    start_time = time.perf_counter()
    try:
        result = await non_stream_completion(
            messages, req.model, req.max_tokens,
            tools=req.tools, tool_choice=req.tool_choice,
        )
    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await record_usage(req.model, messages, "", "error", False,
                           duration_ms=duration_ms, error_detail=str(e))
        raise HTTPException(status_code=502, detail=str(e))

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    output_text = result["choices"][0]["message"].get("content") or ""
    finish_reason = result["choices"][0].get("finish_reason", "stop")
    await record_usage(req.model, messages, output_text, "ok", False,
                       duration_ms=duration_ms, finish_reason=finish_reason)
    return JSONResponse(result)
