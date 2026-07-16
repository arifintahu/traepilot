import os
import hashlib
import secrets
from dotenv import load_dotenv

load_dotenv()

TRAE_BASE_URL = os.getenv("TRAE_BASE_URL", "https://coresg-normal.trae.ai")
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.getenv("BIND_PORT", "8080"))
API_KEY = os.getenv("API_KEY", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(7 * 24 * 3600)))
_session_secret = os.getenv("SESSION_SECRET", "") or secrets.token_hex(32)
SESSION_SIGNING_KEY = hashlib.sha256((_session_secret + DASHBOARD_PASSWORD).encode()).digest()

# Model ids to hide from /v1/models (comma-separated). Defaults to the Claude ids
# that return 4023 on accounts without Claude access.
EXCLUDE_MODELS = {
    m.strip()
    for m in os.getenv("TRAE_EXCLUDE_MODELS", "claude3.5,aws_sdk_claude37_sonnet").split(",")
    if m.strip()
}

# How often the background token health check runs (hours). Runtime-adjustable
# from the dashboard; not persisted (mirrors the in-memory token overwrite).
HEALTHCHECK_INTERVAL_HOURS = float(os.getenv("TRAE_HEALTHCHECK_INTERVAL_HOURS", "12"))

_IDE_TOKEN = os.getenv("TRAE_IDE_TOKEN", "")

# Mirror the headers Trae sends on every authenticated request. Empty values are
# dropped, so we send exactly what Trae sends: e.g. current Trae never sends
# x-ide-version / x-ide-version-type, so leaving those blank just omits them.
# The Authorization header is the same JWT as x-ide-token, prefixed with the
# "Cloud-IDE-JWT" scheme, so it is derived here rather than stored separately.
TRAE_HEADERS = {
    name: value
    for name, value in {
        "authorization":      f"Cloud-IDE-JWT {_IDE_TOKEN}" if _IDE_TOKEN else "",
        "x-app-id":           os.getenv("TRAE_APP_ID", ""),
        "x-device-brand":     os.getenv("TRAE_DEVICE_BRAND", ""),
        "x-device-cpu":       os.getenv("TRAE_DEVICE_CPU", ""),
        "x-device-id":        os.getenv("TRAE_DEVICE_ID", ""),
        "x-device-type":      os.getenv("TRAE_DEVICE_TYPE", ""),
        "x-ide-token":        _IDE_TOKEN,
        "x-ide-version":      os.getenv("TRAE_IDE_VERSION", ""),
        "x-ide-version-code": os.getenv("TRAE_IDE_VERSION_CODE", ""),
        "x-machine-id":       os.getenv("TRAE_MACHINE_ID", ""),
        "x-os-version":       os.getenv("TRAE_OS_VERSION", ""),
        "x-plugin-channel":   os.getenv("TRAE_PLUGIN_CHANNEL", "icube-ai"),
    }.items()
    if value
}


def get_ide_token() -> str:
    """Current IDE token in use by the running proxy."""
    return _IDE_TOKEN


def set_ide_token(token: str) -> None:
    """Overwrite the IDE token in the running process (not persisted to .env).

    Mutates TRAE_HEADERS in place so trae_client — which holds a live reference
    to the same dict — picks up the new token on its next request.
    """
    global _IDE_TOKEN
    _IDE_TOKEN = token
    if token:
        TRAE_HEADERS["authorization"] = f"Cloud-IDE-JWT {token}"
        TRAE_HEADERS["x-ide-token"] = token
    else:
        TRAE_HEADERS.pop("authorization", None)
        TRAE_HEADERS.pop("x-ide-token", None)
