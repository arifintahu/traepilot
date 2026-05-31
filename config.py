import os
from dotenv import load_dotenv

load_dotenv()

TRAE_BASE_URL = os.getenv("TRAE_BASE_URL", "https://trae-api-sg.mchost.guru")
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.getenv("BIND_PORT", "8080"))
API_KEY = os.getenv("API_KEY", "")

TRAE_HEADERS = {
    "x-app-id":            os.getenv("TRAE_APP_ID", ""),
    "x-device-brand":      os.getenv("TRAE_DEVICE_BRAND", ""),
    "x-device-cpu":        os.getenv("TRAE_DEVICE_CPU", ""),
    "x-device-id":         os.getenv("TRAE_DEVICE_ID", ""),
    "x-device-type":       os.getenv("TRAE_DEVICE_TYPE", ""),
    "x-ide-token":         os.getenv("TRAE_IDE_TOKEN", ""),
    "x-ide-version":       os.getenv("TRAE_IDE_VERSION", ""),
    "x-ide-version-code":  os.getenv("TRAE_IDE_VERSION_CODE", ""),
    "x-ide-version-type":  os.getenv("TRAE_IDE_VERSION_TYPE", ""),
    "x-machine-id":        os.getenv("TRAE_MACHINE_ID", ""),
    "x-os-version":        os.getenv("TRAE_OS_VERSION", ""),
}
