#!/bin/bash
# iPhone Backup Tool launcher (English) — double-click to run
# Auto-detects and installs dependencies (Python venv), then opens the web UI
cd "$(dirname "$0")"

echo "======================================"
echo "  iPhone Backup to External Drive"
echo "======================================"

# 1) locate python3
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
    echo ""
    echo "Python3 not found. Trying to trigger the Xcode Command Line Tools installer..."
    xcode-select --install 2>/dev/null
    echo ""
    echo "Please click \"Install\" in the system dialog, then run this launcher again."
    read -r -p "Press Enter to exit..."
    exit 1
fi
echo "Python: $("$PY" --version 2>&1)"

# 2) create venv (first run only)
if [ ! -d .venv ]; then
    echo "First run — creating virtual environment..."
    "$PY" -m venv .venv
    if [ ! -f .venv/bin/python3 ]; then
        echo "venv failed, trying ensurepip..."
        "$PY" -m ensurepip --default-pip >/dev/null 2>&1
        "$PY" -m venv .venv || { echo "Still failing — please report this error"; read -r -p "Press Enter..."; exit 1; }
    fi
fi
PY=".venv/bin/python3"

# 3) install dependencies if missing
if ! "$PY" -c "import pymobiledevice3, fastapi, uvicorn" 2>/dev/null; then
    echo "Installing dependencies (first run only, needs internet)..."
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q "pymobiledevice3==11.43.1"
    if ! "$PY" -c "import pymobiledevice3, fastapi, uvicorn" 2>/dev/null; then
        echo "Dependency install failed — check your network and retry"
        read -r -p "Press Enter to exit..."
        exit 1
    fi
    echo "Dependencies installed"
fi

# 4) start (opens http://127.0.0.1:8787)
echo ""
echo "Starting — your browser will open http://127.0.0.1:8787 ..."
echo "(Keep this window open; closing it stops the server)"
exec "$PY" app.py
