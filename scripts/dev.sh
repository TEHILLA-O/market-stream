#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export MARKETSTREAM_PORT="${MARKETSTREAM_PORT:-8000}"
export MARKETSTREAM_API="http://127.0.0.1:${MARKETSTREAM_PORT}"
python3 -m venv .venv
.venv/bin/python -m pip install -e "./backend[dev]"
.venv/bin/python -m marketstream &
cd frontend
npm install
npm run dev
