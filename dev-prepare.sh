#!/usr/bin/env bash
# Set up the development environment for Printing Press
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3.12}"

echo "==> Checking Python version..."
if ! command -v "$PYTHON" &>/dev/null; then
    echo "Error: $PYTHON not found. Please install Python 3.12+." >&2
    exit 1
fi

echo "==> Creating virtual environment (.venv)..."
"$PYTHON" -m venv .venv

echo "==> Activating virtual environment..."
source .venv/bin/activate

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "==> Creating data directories..."
mkdir -p data books/markdown

echo ""
echo "Done! To run the server:"
echo "  ./run.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload"
