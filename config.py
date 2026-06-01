import os
from dotenv import load_dotenv

load_dotenv()

TRAE_BASE_URL = os.getenv("TRAE_BASE_URL", "https://coresg-normal.trae.ai")
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.getenv("BIND_PORT", "8080"))
API_KEY = os.getenv("API_KEY", "")

# Model ids to hide from /v1/models (comma-separated). Defaults to the Claude ids
# that return 4023 on accounts without Claude access.
EXCLUDE_MODELS = {
    m.strip()
    for m in os.getenv("TRAE_EXCLUDE_MODELS", "claude3.5,aws_sdk_claude37_sonnet").split(",")
    if m.strip()
}

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
