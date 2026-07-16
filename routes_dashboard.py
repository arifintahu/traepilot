import asyncio
import os
import secrets
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import config
import health as token_health  # module name would clash with the /health route below
from config import BIND_PORT, DASHBOARD_PASSWORD, SESSION_MAX_AGE
from deps import require_auth, _client_ip, _is_https
from usage import get_daily, get_history, get_history_detail, get_stats
import session_auth
from session_auth import check_rate_limit, clear_failures, mint_session, record_failure

router = APIRouter()

# ── Usage sub-router ───────────────────────────────────────────────────────────

_usage = APIRouter(prefix="/usage", tags=["usage"])


@_usage.get("/stats")
async def usage_stats(
    period: Literal["24h", "7d", "30d", "all"] = "24h",
    _: None = Depends(require_auth),
):
    return get_stats(period)


@_usage.get("/history")
async def usage_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_auth),
):
    return get_history(limit, offset)


@_usage.get("/history/{request_id}")
async def usage_history_detail(request_id: int, _: None = Depends(require_auth)):
    item = get_history_detail(request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


@_usage.get("/daily")
async def usage_daily(
    days: int = Query(default=30, ge=1, le=365),
    _: None = Depends(require_auth),
):
    return get_daily(days)


router.include_router(_usage)

# ── Misc endpoints ─────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


_MASKED = "••••••"


def _mask(key: str) -> str:
    val = os.getenv(key, "")
    return "(not set)" if not val else _MASKED


@router.get("/config")
async def get_config(_: None = Depends(require_auth)):
    return {
        "TRAE_BASE_URL":         os.getenv("TRAE_BASE_URL", "https://coresg-normal.trae.ai"),
        "BIND_HOST":             os.getenv("BIND_HOST", "127.0.0.1"),
        "BIND_PORT":             BIND_PORT,
        "API_KEY":               _mask("API_KEY"),
        "DASHBOARD_PASSWORD":    _mask("DASHBOARD_PASSWORD"),
        "TRAE_EXCLUDE_MODELS":   os.getenv("TRAE_EXCLUDE_MODELS", "claude3.5,aws_sdk_claude37_sonnet"),
        "TRAE_APP_ID":           os.getenv("TRAE_APP_ID", ""),
        "TRAE_DEVICE_BRAND":     os.getenv("TRAE_DEVICE_BRAND", ""),
        "TRAE_DEVICE_CPU":       os.getenv("TRAE_DEVICE_CPU", ""),
        "TRAE_DEVICE_ID":        _mask("TRAE_DEVICE_ID"),
        "TRAE_DEVICE_TYPE":      os.getenv("TRAE_DEVICE_TYPE", ""),
        "TRAE_IDE_TOKEN":        _MASKED if config.get_ide_token() else "(not set)",
        "TRAE_IDE_VERSION":      os.getenv("TRAE_IDE_VERSION", ""),
        "TRAE_IDE_VERSION_CODE": os.getenv("TRAE_IDE_VERSION_CODE", ""),
        "TRAE_MACHINE_ID":       _mask("TRAE_MACHINE_ID"),
        "TRAE_OS_VERSION":       os.getenv("TRAE_OS_VERSION", ""),
        "TRAE_PLUGIN_CHANNEL":   os.getenv("TRAE_PLUGIN_CHANNEL", "icube-ai"),
    }


# ── IDE token (reveal + in-memory overwrite) ─────────────────────────────────

class _TokenBody(BaseModel):
    token: str


@router.get("/config/ide-token")
async def get_ide_token(_: None = Depends(require_auth)):
    """Return the real token for the reveal toggle (auth-gated)."""
    return {"token": config.get_ide_token()}


@router.put("/config/ide-token")
async def put_ide_token(body: _TokenBody, _: None = Depends(require_auth)):
    """Overwrite the running proxy's IDE token (in-memory; not persisted to .env)."""
    config.set_ide_token(body.token.strip())
    return {"ok": True, "set": bool(config.get_ide_token())}


# ── Token health check ───────────────────────────────────────────────────────

_health = APIRouter(prefix="/trae-health", tags=["trae-health"])


class _IntervalBody(BaseModel):
    hours: float


@_health.get("")
async def health_status(_: None = Depends(require_auth)):
    return token_health.get_state()


@_health.post("/check")
async def health_check_now(_: None = Depends(require_auth)):
    return await token_health.run_check()


@_health.put("/interval")
async def health_set_interval(body: _IntervalBody, _: None = Depends(require_auth)):
    if not (0 < body.hours <= 720):
        raise HTTPException(status_code=400, detail="hours must be between 0 and 720")
    token_health.set_interval(body.hours)
    return token_health.get_state()


router.include_router(_health)


class _LoginBody(BaseModel):
    password: str


@router.post("/auth/login")
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
    resp = Response(status_code=204)
    resp.set_cookie(
        "tp_session", mint_session(),
        max_age=SESSION_MAX_AGE, httponly=True,
        samesite="lax", secure=_is_https(request), path="/",
    )
    return resp


@router.post("/auth/logout")
async def auth_logout():
    resp = Response(status_code=204)
    resp.set_cookie("tp_session", "", max_age=0, httponly=True, samesite="lax", path="/")
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dashboard.html not found")
