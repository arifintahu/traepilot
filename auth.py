"""
auth.py - manual helper to extract Trae IDE credentials.
Run once: python auth.py > .env.local
Not used at runtime; the proxy reads from env vars directly.
"""
import sqlite3
import json
import sys
import os

TRAE_DB_PATHS = [
    os.path.expanduser("~/.trae/User/globalStorage/state.vscdb"),
    os.path.expanduser("~/.config/trae/User/globalStorage/state.vscdb"),
]


def extract_trae_credentials(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value FROM ItemTable WHERE key = ?", ("trae.account.ideToken",))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError("ideToken not found in Trae DB")
    token_data = json.loads(row[0])
    return token_data


def main():
    for db_path in TRAE_DB_PATHS:
        if os.path.exists(db_path):
            try:
                creds = extract_trae_credentials(db_path)
                print(f'TRAE_IDE_TOKEN={creds.get("token", "")}')
                print(f'TRAE_MACHINE_ID={creds.get("machineId", "")}')
                print(f'TRAE_DEVICE_ID={creds.get("deviceId", "")}')
                print(f'TRAE_APP_ID={creds.get("appId", "")}')
                return
            except Exception as e:
                print(f"Error reading {db_path}: {e}", file=sys.stderr)
    print("No Trae DB found. Set TRAE_IDE_TOKEN manually.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
