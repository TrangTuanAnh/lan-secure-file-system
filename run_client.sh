#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/coordinator-node"

if [[ ! -d "$CLIENT_DIR" ]]; then
  echo "Khong tim thay thu muc coordinator-node: $CLIENT_DIR" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Khong tim thay Python. Hay cai dat python3 truoc khi chay client." >&2
  exit 1
fi

cd "$CLIENT_DIR"
exec "$PYTHON_BIN" main.py
  