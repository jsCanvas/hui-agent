#!/usr/bin/env bash
# Background socket relay (detached; no UI focus change).
# Usage: run-cursor-socket-background.sh [watch_minutes]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MCP="$ROOT/mcp-server"
PY="$MCP/.venv/bin/python"
WATCH="${1:-720}"
LOG="${HOME}/.hui-agent/logs/cursor-socket.log"

mkdir -p "$(dirname "$LOG")"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

nohup "$PY" "$ROOT/scripts/cursor-socket-client.py" --watch-minutes "$WATCH" >>"$LOG" 2>&1 &
echo "$!"
