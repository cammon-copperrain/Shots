#!/bin/bash
# Double-click to start Shots. First run sets everything up (takes a minute).
cd "$(dirname "$0")" || exit 1

PY=$(command -v python3)
if [ -z "$PY" ]; then
  echo "python3 not found. Install it with:  brew install python   (or run: xcode-select --install)"
  read -r -p "Press Return to close."; exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: creating Python environment..."
  "$PY" -m venv .venv || exit 1
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt || { read -r -p "Install failed. Press Return to close."; exit 1; }
  touch .venv/.installed
fi
if [ ! -f config.json ]; then
  cp config.example.json config.json
  echo "Created config.json - open it and paste your fal key, then restart Shots."
fi

PORT=$(.venv/bin/python -c "import json;print(json.load(open('config.json')).get('port',8765))")
if curl -s "http://127.0.0.1:$PORT/api/config" >/dev/null 2>&1; then
  echo "Shots is already running."
  open "http://127.0.0.1:$PORT"; exit 0
fi

(sleep 1.5 && open "http://127.0.0.1:$PORT") &
echo "Shots running at http://127.0.0.1:$PORT  (close this window to stop it)"
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port "$PORT"
