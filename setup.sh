#!/usr/bin/env bash
# One-time setup (macOS/Linux): creates .venv and installs dependencies.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
$PY -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt
echo "Done. In VS Code: Ctrl/Cmd+Shift+P -> 'Python: Select Interpreter' -> .venv, then press F5."
