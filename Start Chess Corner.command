#!/bin/bash
# Chess Corner launcher - double-click it in Finder.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python isn't installed on this computer."
  echo "Install it from https://www.python.org/downloads/, then run this again."
  open https://www.python.org/downloads/
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

# private Python environment with the chess library, created on first run only
if [ ! -x .venv/bin/python ]; then
  echo "Setting up (one time, needs internet)..."
  python3 -m venv .venv && .venv/bin/python -m pip install --quiet chess || {
    read -n 1 -s -r -p "Setup failed. Press any key to close..."; exit 1; }
fi

# start the helper in the background (it exits by itself if already running), then open the dashboard
nohup .venv/bin/python hub/server.py >/dev/null 2>&1 &
sleep 3
open http://127.0.0.1:8777
