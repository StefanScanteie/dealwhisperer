#!/bin/bash
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null 2>&1 || {
  echo "python3 not found. Install Python 3.9+ and add it to PATH."; exit 1
}

[ -f ".env" ] || { echo ".env not found — run: cp .env.example .env"; exit 1; }

python3 -c "import flask, anthropic, requests, dotenv" 2>/dev/null || {
  echo "Installing dependencies…"
  pip3 install -r requirements.txt
}

(sleep 2 && open "http://localhost:${PORT:-5001}") &
python3 app.py
