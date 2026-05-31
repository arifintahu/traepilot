"""
auth.py - extract Trae IDE credentials for TraePilot.

Usage:
    python auth.py            # preview KEY=VALUE lines on stdout, notes on stderr
    python auth.py --write     # fill .env in place (replace values, drop duplicates)
    python auth.py --write PATH # target a file other than ./.env

Why this reads logs instead of the SQLite DB:
Older Trae stored the IDE token as plaintext JSON under the key
"trae.account.ideToken" in state.vscdb. Current Trae (2.x) encrypts the account
blob in globalStorage/storage.json, so it can no longer be read directly. The
trae.ai-code-completion extension, however, logs every upstream request's
headers - which include the live x-ide-token (a JWT) plus the machine/device/app
ids and the real API host. We parse the newest such entry.

Token expired or logged out? Use Trae briefly (trigger a completion or chat) so
it logs a fresh request, then re-run this script.
"""
import glob
import json
import os
import re
import sqlite3
import sys
from urllib.parse import urlsplit

# Trae request header -> env var TraePilot reads (see config.py).
HEADER_TO_ENV = {
    "x-ide-token": "TRAE_IDE_TOKEN",
    "x-machine-id": "TRAE_MACHINE_ID",
    "x-device-id": "TRAE_DEVICE_ID",
    "x-app-id": "TRAE_APP_ID",
    "x-device-brand": "TRAE_DEVICE_BRAND",
    "x-device-cpu": "TRAE_DEVICE_CPU",
    "x-device-type": "TRAE_DEVICE_TYPE",
    "x-os-version": "TRAE_OS_VERSION",
    "x-ide-version": "TRAE_IDE_VERSION",
    "x-ide-version-code": "TRAE_IDE_VERSION_CODE",
    "x-plugin-channel": "TRAE_PLUGIN_CHANNEL",
}

_HEADERS_RE = re.compile(r"request:\s*headers:\s*(\{.*\})\s*$")
_URL_RE = re.compile(r"https?://[^/\s\"]+")
_ENV_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def trae_data_dirs() -> list[str]:
    """Trae per-user data directories that exist, most likely first."""
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    roots = []
    for name in ("Trae", "Trae CN", "trae"):
        roots += [
            os.path.join(appdata, name),                                # Windows
            os.path.join(home, "Library", "Application Support", name),  # macOS
            os.path.join(home, ".config", name),                        # Linux
        ]
    return [r for r in roots if os.path.isdir(r)]


def completion_logs() -> list[str]:
    """trae.ai-code-completion log files, newest first."""
    logs: list[str] = []
    for root in trae_data_dirs():
        logs += glob.glob(
            os.path.join(root, "logs", "**", "trae.ai-code-completion", "*.log"),
            recursive=True,
        )
    logs.sort(key=os.path.getmtime, reverse=True)
    return logs


def extract_from_logs() -> tuple[dict | None, str | None]:
    """Headers + base URL from the newest logged request that carried a token."""
    for log in completion_logs():
        headers = None
        base_url = None
        try:
            with open(log, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = _HEADERS_RE.search(line)
                    if m:
                        try:
                            parsed = json.loads(m.group(1))
                        except json.JSONDecodeError:
                            continue
                        lowered = {k.lower(): v for k, v in parsed.items()}
                        if lowered.get("x-ide-token"):
                            headers = lowered  # keep the most recent in this file
                    elif base_url is None and "/api/ide/" in line:
                        found = _URL_RE.search(line)
                        if found:
                            parts = urlsplit(found.group(0))
                            base_url = f"{parts.scheme}://{parts.netloc}"
        except OSError:
            continue
        if headers:
            return headers, base_url
    return None, None


def extract_from_db() -> dict | None:
    """Legacy fallback: plaintext token in older Trae's SQLite DB."""
    for root in trae_data_dirs():
        db = os.path.join(root, "User", "globalStorage", "state.vscdb")
        if not os.path.exists(db):
            continue
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT value FROM ItemTable WHERE key = ?", ("trae.account.ideToken",))
            row = cur.fetchone()
            conn.close()
        except sqlite3.Error:
            continue
        if row:
            data = json.loads(row[0])
            return {
                "x-ide-token": data.get("token", ""),
                "x-machine-id": data.get("machineId", ""),
                "x-device-id": data.get("deviceId", ""),
                "x-app-id": data.get("appId", ""),
            }
    return None


def build_pairs(headers: dict) -> dict[str, str]:
    """Ordered env var -> value for every header that was present and non-empty."""
    pairs = {}
    for header, env in HEADER_TO_ENV.items():
        value = headers.get(header)
        if value:
            pairs[env] = value
    return pairs


def update_env_file(pairs: dict[str, str], path: str) -> tuple[int, int]:
    """Set each KEY in `path` in place: replace the first matching line, drop any
    later duplicates, append keys that are missing. Comments, blank lines and
    unrelated keys are left untouched. Returns (replaced, added)."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    out: list[str] = []
    seen: set[str] = set()
    replaced = 0
    for line in lines:
        match = _ENV_KEY_RE.match(line)
        key = match.group(1) if match else None
        if key in pairs:
            if key in seen:
                continue  # discard duplicate occurrences of a managed key
            out.append(f"{key}={pairs[key]}")
            seen.add(key)
            replaced += 1
        else:
            out.append(line)

    added = 0
    for key, value in pairs.items():
        if key not in seen:
            out.append(f"{key}={value}")
            added += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return replaced, added


def main() -> None:
    args = sys.argv[1:]
    write = "--write" in args or "-w" in args
    positional = [a for a in args if not a.startswith("-")]
    env_path = positional[0] if positional else ".env"

    headers, base_url = extract_from_logs()
    source = "Trae completion log"
    if not headers:
        headers = extract_from_db()
        source = "Trae SQLite DB (legacy)"
    if not headers:
        print(
            "Could not find Trae credentials.\n"
            "- Make sure Trae is installed and you are signed in.\n"
            "- Open Trae and trigger a code completion or chat so it logs a\n"
            "  request, then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    pairs = build_pairs(headers)
    print(f"# extracted from {source}", file=sys.stderr)

    if write:
        replaced, added = update_env_file(pairs, env_path)
        print(
            f"# {env_path}: {replaced} updated, {added} added (duplicates removed)",
            file=sys.stderr,
        )
    else:
        for key, value in pairs.items():
            print(f"{key}={value}")

    if base_url:
        print(f"# Trae is talking to {base_url}", file=sys.stderr)
        print(f"#   if requests fail, set TRAE_BASE_URL={base_url}", file=sys.stderr)
    if not write:
        print(
            "# review the lines above, then fill .env:  python auth.py --write",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
