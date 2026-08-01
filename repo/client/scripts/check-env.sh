#!/usr/bin/env bash
# 检查 Tauri 开发环境
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Python MCP"
if [[ ! -x mcp-server/.venv/bin/python ]]; then
  echo "请先: cd mcp-server && python3.12 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

echo "==> UI"
if [[ ! -d ui/node_modules ]]; then
  (cd ui && npm install)
fi

echo "==> Tauri CLI"
if [[ ! -d node_modules ]]; then
  npm install
fi

python3 scripts/gen-icons.py

if ! command -v cargo >/dev/null 2>&1; then
  echo ""
  echo "未检测到 Rust。请安装: https://rustup.rs"
  echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
  exit 1
fi

echo ""
echo "环境 OK。运行: npm run dev"
