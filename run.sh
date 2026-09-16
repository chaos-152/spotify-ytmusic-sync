#!/usr/bin/env bash
# ==============================================================================
# One-Click Launcher for Spotify -> YouTube Music Sync (Linux & macOS)
# ==============================================================================
set -e

# Change to script directory
cd "$(dirname "$0")"

echo "============================================================"
echo "   Spotify ⇄ YT Music Sync Launcher"
echo "============================================================"

# 1. Check Python 3
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    echo "❌ Error: Python 3 is not installed or not in PATH."
    echo "   Please install Python 3.10+ from https://www.python.org/"
    exit 1
fi

# Check version >= 3.10
$PY_BIN -c '
import sys
if sys.version_info < (3, 10):
    print(f"❌ Error: Python 3.10+ required. Found {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)
'

# 2. Virtual Environment Setup
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment in ./venv..."
    $PY_BIN -m venv venv
fi

# Activate venv
if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    # shellcheck disable=SC1091
    source venv/Scripts/activate
fi

# 3. Dependencies
if ! python -c "import fastapi, uvicorn, ytmusicapi" >/dev/null 2>&1; then
    echo "📥 Installing required packages from requirements.txt..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo "✓ Packages installed."
fi

# 4. Launch Application
PORT=8000
HOST="127.0.0.1"
URL="http://${HOST}:${PORT}"

echo ""
echo "🚀 Starting server at ${URL}..."
echo "   Press Ctrl+C to stop."
echo "============================================================"

# Try to open default browser after server starts (non-blocking)
(
    sleep 1.5
    if command -v xdg-open >/dev/null 2>&1 && [ -n "$DISPLAY" ]; then
        xdg-open "$URL" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
    fi
) &

exec uvicorn backend.main:app --host "$HOST" --port "$PORT"
