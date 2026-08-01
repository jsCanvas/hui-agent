#!/usr/bin/env bash
# 一键启动 Cursor Socket Relay（cursor-socket-client.py）
# 用法: ./scripts/connect-cursor-socket.sh [--foreground]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DAEMON_PORT="${HUI_AGENT_DAEMON_PORT:-18766}"
LOG_DIR="${HOME}/.hui-agent"
LOG_FILE="${LOG_DIR}/cursor-socket.log"
FOREGROUND=false

for arg in "$@"; do
  case "$arg" in
    --foreground|-f) FOREGROUND=true ;;
  esac
done

health_json() {
  curl -sf --max-time 2 "http://127.0.0.1:${DAEMON_PORT}/health" 2>/dev/null || true
}

cursor_online() {
  local json
  json="$(health_json)"
  [[ -n "$json" ]] || return 1
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent',{}).get('cursor_online', False))" <<<"$json"
}

companion_online() {
  local json
  json="$(health_json)"
  [[ -n "$json" ]] || return 1
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent',{}).get('companion_online', False))" <<<"$json"
}

if [[ -z "$(health_json)" ]]; then
  echo "✗ Daemon 未运行（:${DAEMON_PORT}）"
  echo "  请先: cd hui-agent/repo/client && npm run dev"
  exit 1
fi

if [[ "$(cursor_online)" == "True" ]]; then
  echo "✓ cursor_online: true（Socket Relay 已连接）"
  health_json | python3 -m json.tool 2>/dev/null | head -20
  exit 0
fi

echo "ℹ npm run dev 会自动启动 cursor-socket-client；若仍为 offline 可手动运行本脚本。"

if pgrep -f "scripts/cursor-socket-client.py" >/dev/null 2>&1; then
  echo "… cursor-socket-client 进程已存在，等待注册（最多 15s）"
  for _ in $(seq 1 15); do
    sleep 1
    if [[ "$(cursor_online)" == "True" ]]; then
      echo "✓ cursor_online: true"
      exit 0
    fi
  done
  echo "⚠ 进程在跑但 cursor_online 仍为 false，请查看 ${LOG_FILE}"
  exit 1
fi

mkdir -p "$LOG_DIR"
CMD=(python3 "$ROOT/scripts/cursor-socket-client.py")

if $FOREGROUND; then
  echo "→ 前台运行 Cursor Socket Relay（Ctrl+C 退出）"
  exec "${CMD[@]}"
fi

echo "→ 后台启动 Cursor Socket Relay"
nohup "${CMD[@]}" >>"$LOG_FILE" 2>&1 &
PID=$!
echo "  PID: $PID"
echo "  日志: $LOG_FILE"

for _ in $(seq 1 20); do
  sleep 1
  if [[ "$(cursor_online)" == "True" ]]; then
    echo "✓ cursor_online: true"
    companion="$(companion_online)"
    echo "  companion_online: $companion"
    exit 0
  fi
done

echo "⚠ 已启动但尚未 cursor_online，请稍候或查看日志:"
echo "  tail -f $LOG_FILE"
exit 1
