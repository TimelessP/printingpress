#!/usr/bin/env bash
# Run the Printing Press FastAPI server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [[ ! -d .venv ]]; then
    echo "Error: .venv not found. Run ./dev-prepare.sh first." >&2
    exit 1
fi
source .venv/bin/activate

# Default settings
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

echo "Starting Printing Press on http://${HOST}:${PORT}"

if [[ "$RELOAD" == "1" ]]; then
    exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
else
    exec uvicorn app.main:app --host "$HOST" --port "$PORT"
fi
