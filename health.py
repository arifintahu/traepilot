"""Background token health check.

Periodically calls Trae's model-list endpoint with the current token headers to
detect an expired / revoked / unavailable IDE token. Uses model_list rather than
a chat completion so the check consumes no message quota. The interval is
runtime-adjustable from the dashboard.
"""
import asyncio
import time

import config
from trae_client import list_models

_MIN_INTERVAL_S = 60

_state = {
    "status": "unknown",    # ok | error | unknown
    "checked_at": None,     # epoch seconds of the last completed check
    "next_check_at": None,  # epoch seconds the loop will next check
    "detail": None,         # human-readable result / error message
    "model_count": None,
}

_interval_hours = config.HEALTHCHECK_INTERVAL_HOURS
_wake = asyncio.Event()  # set to reschedule the loop (interval change)


def _interval_seconds() -> float:
    return max(_interval_hours * 3600, _MIN_INTERVAL_S)


def get_state() -> dict:
    return {**_state, "interval_hours": _interval_hours}


def set_interval(hours: float) -> None:
    """Change the check interval and wake the loop so it reschedules."""
    global _interval_hours
    _interval_hours = hours
    _wake.set()


async def run_check() -> dict:
    """Run one health check now and record the result in shared state."""
    try:
        models = await list_models()
        _state["status"] = "ok"
        _state["model_count"] = len(models)
        _state["detail"] = f"{len(models)} models available"
    except Exception as exc:
        _state["status"] = "error"
        _state["model_count"] = None
        _state["detail"] = str(exc) or exc.__class__.__name__
    _state["checked_at"] = int(time.time())
    return get_state()


async def health_loop() -> None:
    """Check once at startup, then every interval (interruptible for reschedule)."""
    while True:
        await run_check()
        _state["next_check_at"] = int(time.time() + _interval_seconds())
        try:
            await asyncio.wait_for(_wake.wait(), timeout=_interval_seconds())
        except asyncio.TimeoutError:
            pass
        _wake.clear()
