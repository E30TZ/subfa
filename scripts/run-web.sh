#!/bin/sh
# Start the SubFa web app (macOS / Linux). Creates and reuses .venv.
set -e
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements/web.txt
exec uvicorn web.app:app --host 0.0.0.0 --port 8000
