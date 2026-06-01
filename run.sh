#!/usr/bin/env bash
# One-command launcher for the Klenty SEO Dashboard.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Use the same Python the MCP server uses
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.11}"
VENV="$DIR/.venv"

if [ ! -d "$VENV" ]; then
  echo "→ Creating virtualenv..."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi

echo "→ Starting dashboard at http://localhost:8501"
"$VENV/bin/streamlit" run app.py --server.headless true --server.port 8501
