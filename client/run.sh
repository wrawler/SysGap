#!/usr/bin/env sh
set -eu

CLIENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$CLIENT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python 3.10 or newer was not found on PATH." >&2
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "[ERROR] SysGap requires Python 3.10 or newer." >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "[SETUP] Creating an isolated Python environment..."
    python3 -m venv .venv
fi

if [ ! -f ".venv/.sysgap-dependencies-installed" ] || [ requirements.txt -nt ".venv/.sysgap-dependencies-installed" ]; then
    echo "[SETUP] Installing client requirements..."
    ".venv/bin/python" -m pip install -r requirements.txt
    : > ".venv/.sysgap-dependencies-installed"
fi

exec ".venv/bin/python" cli.py run "$@"
