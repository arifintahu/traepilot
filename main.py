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
    messages: list
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
            try:
                async for chunk in stream_completion(messages, req.model, req.max_tokens):
                    if chunk == "[DONE]":
                        yield "data: [DONE]\n\n"
                    else:
                        yield chunk
            except Exception as e:
                err = {"error": {"message": str(e), "type": "upstream_error"}}
                yield f"data: {json.dumps(err)}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        result = await non_stream_completion(messages, req.model, req.max_tokens)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return JSONResponse(result)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
