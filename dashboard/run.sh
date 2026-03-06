#!/usr/bin/env bash
# Start the Trading Bot Dashboard on port 5555
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/../venv"

if [ -f "$VENV/bin/activate" ]; then
    source "$VENV/bin/activate"
fi

cd "$DIR"
exec python3 app.py
