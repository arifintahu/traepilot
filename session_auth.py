"""Cookie-based session authentication for the TraePilot dashboard.

Named session_auth.py to avoid collision with auth.py (the Trae credential
extraction CLI — do not modify that file).
"""
import hmac
import hashlib
import time
from typing import Optional

from config import SESSION_SIGNING_KEY, SESSION_MAX_AGE

# On every failed login attempt we await asyncio.sleep(FAILURE_DELAY) to slow
# brute-force attacks.  Tests monkeypatch this to 0 so they don't slow down.
FAILURE_DELAY: float = 0.5

# Per-IP brute-force tracking: map of ip -> list of failure timestamps (float).
_failures: dict[str, list[float]] = {}

_WINDOW = 15 * 60   # 15-minute sliding window
_MAX_FAILURES = 5


def _sig(exp: int) -> str:
    """Compute HMAC-SHA256 signature for the given expiry timestamp."""
    msg = f"v1:{exp}".encode()
    return hmac.new(SESSION_SIGNING_KEY, msg, hashlib.sha256).hexdigest()


def mint_session(max_age: Optional[int] = None) -> str:
    """Return a signed session cookie value: 'v1:<expiry_unix>:<hex_sig>'."""
    age = max_age if max_age is not None else SESSION_MAX_AGE
    exp = int(time.time()) + age
    sig = _sig(exp)
    return f"v1:{exp}:{sig}"


def verify_session(cookie_value: Optional[str]) -> bool:
    """Return True iff the cookie value is well-formed, unexpired, and has a valid sig."""
    if not cookie_value:
        return False
    try:
        parts = cookie_value.split(":")
        if len(parts) != 3 or parts[0] != "v1":
            return False
        exp = int(parts[1])
        given_sig = parts[2]
    except Exception:
        return False
    if time.time() > exp:
        return False
    expected_sig = _sig(exp)
    return hmac.compare_digest(expected_sig, given_sig)


def check_rate_limit(ip: str) -> int:
    """Return seconds the client must wait (0 = allowed).

    Tracks at most _MAX_FAILURES failures per ip in a _WINDOW-second window.
    Prunes stale entries on each call.
    """
    now = time.time()
    bucket = _failures.get(ip, [])
    # Prune timestamps outside the window
    bucket = [t for t in bucket if now - t < _WINDOW]
    _failures[ip] = bucket
    if len(bucket) >= _MAX_FAILURES:
        oldest = bucket[0]
        wait = int(_WINDOW - (now - oldest)) + 1
        return max(wait, 1)
    return 0


def record_failure(ip: str) -> None:
    """Record a failed login attempt for the given IP."""
    now = time.time()
    bucket = _failures.get(ip, [])
    bucket = [t for t in bucket if now - t < _WINDOW]
    bucket.append(now)
    _failures[ip] = bucket


def clear_failures(ip: str) -> None:
    """Clear recorded failures for the given IP on successful login."""
    _failures.pop(ip, None)
