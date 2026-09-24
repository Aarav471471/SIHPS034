#!/usr/bin/env bash
# Start the MetriX API in development mode (SQLite + in-process workers).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/backend"

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python -m venv .venv --system-site-packages
  ./.venv/Scripts/python.exe -m pip install -r requirements.txt 2>/dev/null \
    || ./.venv/bin/python -m pip install -r requirements.txt
fi

[ -f "$root/.env" ] || cp "$root/.env.example" "$root/.env"

py="./.venv/Scripts/python.exe"; [ -x "$py" ] || py="./.venv/bin/python"
echo "MetriX API  ->  http://localhost:8000/docs"
exec "$py" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
