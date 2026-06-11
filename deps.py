import secrets
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import API_KEY, DASHBOARD_PASSWORD
from session_auth import verify_session

security = HTTPBearer(auto_error=False)


def _is_https(request: Request) -> bool:
    """Detect HTTPS even behind a reverse proxy that sets X-Forwarded-Proto."""
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "") == "https"
    )


def _client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Accepts Bearer API key OR valid session cookie. Open if neither is set."""
    if not API_KEY and not DASHBOARD_PASSWORD:
        return
    if API_KEY and credentials and secrets.compare_digest(credentials.credentials, API_KEY):
        return
    if DASHBOARD_PASSWORD and verify_session(request.cookies.get("tp_session")):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Bearer-only guard for /v1/chat/completions. Open if API_KEY is unset."""
    if not API_KEY:
        return
    if credentials and secrets.compare_digest(credentials.credentials, API_KEY):
        return
    raise HTTPException(status_code=401, detail="Invalid API key")
