import time
import json
from contextlib import asynccontextmanager
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import BIND_HOST, BIND_PORT, API_KEY
from trae_client import stream_completion, non_stream_completion, list_models
from usage import init_db, record_usage, get_stats, get_history, get_daily


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TraePilot", version="1.0.0", lifespan=lifespan)
security = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials | None = None) -> None:
    if not API_KEY:
        return
    if not credentials or credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False
    max_tokens: Optional[int] = None


@app.get("/v1/models")
async def get_models():
    try:
        models = await list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    if req.stream:
        async def event_stream():
            accumulated = []
            status = "ok"
            try:
                async for chunk in stream_completion(messages, req.model, req.max_tokens):
                    if chunk == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    yield chunk
                    try:
                        delta = json.loads(chunk[6:])["choices"][0]["delta"].get("content", "")
                        if delta:
                            accumulated.append(delta)
                    except Exception:
                        pass
            except Exception as e:
                status = "error"
                err = {"error": {"message": str(e), "type": "upstream_error"}}
                yield f"data: {json.dumps(err)}\n\n"
            finally:
                await record_usage(
                    req.model, messages, "".join(accumulated), status, True
                )
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        result = await non_stream_completion(messages, req.model, req.max_tokens)
    except Exception as e:
        await record_usage(req.model, messages, "", "error", False)
        raise HTTPException(status_code=502, detail=str(e))

    output_text = result["choices"][0]["message"]["content"]
    await record_usage(req.model, messages, output_text, "ok", False)
    return JSONResponse(result)


# ── Usage API ──────────────────────────────────────────────────────────────────

usage_router = APIRouter(prefix="/usage", tags=["usage"])


@usage_router.get("/stats")
async def usage_stats(
    period: Literal["24h", "7d", "30d", "all"] = "24h",
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_stats(period)


@usage_router.get("/history")
async def usage_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_history(limit, offset)


@usage_router.get("/daily")
async def usage_daily(
    days: int = Query(default=30, ge=1, le=365),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    verify_api_key(credentials)
    return get_daily(days)


app.include_router(usage_router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
