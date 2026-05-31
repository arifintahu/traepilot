import time
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import BIND_HOST, BIND_PORT, API_KEY
from trae_client import stream_completion, non_stream_completion, list_models

app = FastAPI(title="TraePilot", version="1.0.0")
security = HTTPBearer(auto_error=False)


def verify_api_key(credentials=None):
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
    # Not supported. Trae serves chat through a native agent protocol
    # (POST /api/ide/v2/llm_raw_chat, handled by Trae's ai-agent binary over
    # ByteDance's TTNet stack). It is not OpenAI-compatible, the request body is
    # assembled inside a native binary, and the call bypasses HTTP proxies, so it
    # cannot be replayed here. /v1/models and /health work. See README.
    raise HTTPException(
        status_code=501,
        detail=(
            "chat/completions is not supported: Trae routes chat through a native "
            "agent protocol (/api/ide/v2/llm_raw_chat) that is not OpenAI-compatible "
            "and cannot be proxied. /v1/models and /health do work."
        ),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
