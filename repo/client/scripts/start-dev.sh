#!/usr/bin/env bash
# 本地开发：启动 Edge TTS Proxy + MCP Server（stdio）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/mcp-server"

if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -e ".[dev]"
fi

export TTS_PROXY_PORT="${TTS_PROXY_PORT:-8896}"
export EDGE_TTS_VOICE="${EDGE_TTS_VOICE:-zh-CN-XiaoxiaoNeural}"

echo "==> Edge TTS proxy :$TTS_PROXY_PORT"
.venv/bin/python -m hui_mcp.voice.tts_proxy &
TTS_PID=$!
trap 'kill $TTS_PID 2>/dev/null || true' EXIT

sleep 0.5
curl -sf "http://127.0.0.1:${TTS_PROXY_PORT}/health" | head -c 200
echo ""
echo "==> MCP server (stdio)"
exec .venv/bin/python -m hui_mcp
