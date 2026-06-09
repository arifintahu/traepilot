import os
import time
import json
import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BIND_HOST, BIND_PORT, API_KEY, DASHBOARD_PASSWORD, SESSION_MAX_AGE
from trae_client import stream_completion, non_stream_completion, list_models
from usage import init_db, record_usage, get_stats, get_history, get_daily
import session_auth
from session_auth import mint_session, verify_session, check_rate_limit, record_failure, clear_failures


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Warn if the proxy is accessible on a non-local interface without any auth.
    _local = ("127.0.0.1", "localhost", "::1")
    if BIND_HOST not in _local and not API_KEY and not DASHBOARD_PASSWORD:
        print(
            "\n*** WARNING: TraePilot is bound to a non-local interface "
            f"({BIND_HOST}) with no API_KEY or DASHBOARD_PASSWORD set. "
            "The proxy is completely unauthenticated — anyone on the network "
            "can use it. Set API_KEY and/or DASHBOARD_PASSWORD in your .env. ***\n"
        )
    yield


app = FastAPI(title="TraePilot", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
security = HTTPBearer(auto_error=False)


def _is_https(request: Request) -> bool:
    """Detect HTTPS even behind a reverse proxy that sets X-Forwarded-Proto."""
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "") == "https"
    )


def _client_ip(request: Request) -> str:
    """Return the client IP.

    If the proxy is behind a trusted reverse proxy the real client is the last
    hop in X-Forwarded-For.  We use the last entry (rightmost) so that a
    downstream client cannot spoof IP by adding their own header.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Dependency: accepts Bearer API key OR valid session cookie.

    Back-compat: if neither API_KEY nor DASHBOARD_PASSWORD is set everything
    is open (same as before this feature was added).
    """
    if not API_KEY and not DASHBOARD_PASSWORD:
        return  # auth disabled
    if API_KEY and credentials and secrets.compare_digest(credentials.credentials, API_KEY):
        return
    if DASHBOARD_PASSWORD and verify_session(request.cookies.get("tp_session")):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Dependency: Bearer-only guard used on POST /v1/chat/completions.

    Session cookie does NOT grant access to the chat endpoint — that keeps
    API clients and dashboard viewers clearly separated.
    If API_KEY is unset the endpoint remains open.
    """
    if not API_KEY:
        return
    if credentials and secrets.compare_digest(credentials.credentials, API_KEY):
        return
    raise HTTPException(status_code=401, detail="Invalid API key")


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


@app.get("/v1/models")
async def get_models():
    try:
        models = await list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, _: None = Depends(require_bearer)):
    messages = [m.model_dump(exclude_none=True) for m in req.messages]

    if req.stream:
        async def event_stream():
            accumulated = []
            status = "ok"
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
                        delta = json.loads(chunk[6:])["choices"][0]["delta"]
                        text = delta.get("content") or ""
                        if text:
                            accumulated.append(text)
                    except Exception:
                        pass
                else:
                    status = "error"
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
        result = await non_stream_completion(
            messages, req.model, req.max_tokens,
            tools=req.tools, tool_choice=req.tool_choice,
        )
    except Exception as e:
        await record_usage(req.model, messages, "", "error", False)
        raise HTTPException(status_code=502, detail=str(e))

    output_text = result["choices"][0]["message"].get("content") or ""
    await record_usage(req.model, messages, output_text, "ok", False)
    return JSONResponse(result)


# ── Usage API ──────────────────────────────────────────────────────────────────

usage_router = APIRouter(prefix="/usage", tags=["usage"])


@usage_router.get("/stats")
async def usage_stats(
    period: Literal["24h", "7d", "30d", "all"] = "24h",
    _: None = Depends(require_auth),
):
    return get_stats(period)


@usage_router.get("/history")
async def usage_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_auth),
):
    return get_history(limit, offset)


@usage_router.get("/daily")
async def usage_daily(
    days: int = Query(default=30, ge=1, le=365),
    _: None = Depends(require_auth),
):
    return get_daily(days)


app.include_router(usage_router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


_MASKED = "••••••"


def _mask(key: str) -> str:
    # Returns "(not set)" vs "••••••" intentionally — callers can tell whether a
    # key is configured without seeing its value. Auth required to reach this endpoint.
    val = os.getenv(key, "")
    if not val:
        return "(not set)"
    return _MASKED


@app.get("/config")
async def get_config(
    _: None = Depends(require_auth),
):
    return {
        "TRAE_BASE_URL":         os.getenv("TRAE_BASE_URL", "https://coresg-normal.trae.ai"),
        "BIND_HOST":             os.getenv("BIND_HOST", "127.0.0.1"),
        "BIND_PORT":             BIND_PORT,  # already int from config.py
        "API_KEY":               _mask("API_KEY"),
        "DASHBOARD_PASSWORD":    _mask("DASHBOARD_PASSWORD"),
        "TRAE_EXCLUDE_MODELS":   os.getenv("TRAE_EXCLUDE_MODELS", "claude3.5,aws_sdk_claude37_sonnet"),
        "TRAE_APP_ID":           os.getenv("TRAE_APP_ID", ""),
        "TRAE_DEVICE_BRAND":     os.getenv("TRAE_DEVICE_BRAND", ""),
        "TRAE_DEVICE_CPU":       os.getenv("TRAE_DEVICE_CPU", ""),
        "TRAE_DEVICE_ID":        _mask("TRAE_DEVICE_ID"),
        "TRAE_DEVICE_TYPE":      os.getenv("TRAE_DEVICE_TYPE", ""),
        "TRAE_IDE_TOKEN":        _mask("TRAE_IDE_TOKEN"),
        "TRAE_IDE_VERSION":      os.getenv("TRAE_IDE_VERSION", ""),
        "TRAE_IDE_VERSION_CODE": os.getenv("TRAE_IDE_VERSION_CODE", ""),
        "TRAE_MACHINE_ID":       _mask("TRAE_MACHINE_ID"),
        "TRAE_OS_VERSION":       os.getenv("TRAE_OS_VERSION", ""),
        "TRAE_PLUGIN_CHANNEL":   os.getenv("TRAE_PLUGIN_CHANNEL", "icube-ai"),
    }


# ── Auth endpoints ─────────────────────────────────────────────────────────────

# CSRF note: all cookie-authed endpoints are GET reads; the login POST is a
# shared-password form (not per-user tokens), so login CSRF would only let an
# attacker log someone in — not extract data.  Therefore no CSRF token is needed.

class _LoginBody(BaseModel):
    password: str


@app.post("/auth/login")
async def auth_login(body: _LoginBody, request: Request):
    if not DASHBOARD_PASSWORD:
        raise HTTPException(status_code=400, detail="Dashboard auth disabled")

    ip = _client_ip(request)
    wait = check_rate_limit(ip)
    if wait:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many failed attempts"},
            headers={"Retry-After": str(wait)},
        )

    if not secrets.compare_digest(body.password, DASHBOARD_PASSWORD):
        record_failure(ip)
        await asyncio.sleep(session_auth.FAILURE_DELAY)
        raise HTTPException(status_code=401, detail="Wrong password")

    clear_failures(ip)
    secure = _is_https(request)
    resp = Response(status_code=204)
    resp.set_cookie(
        "tp_session",
        mint_session(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return resp


@app.post("/auth/logout")
async def auth_logout():
    resp = Response(status_code=204)
    resp.set_cookie(
        "tp_session",
        "",
        max_age=0,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dashboard.html not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
