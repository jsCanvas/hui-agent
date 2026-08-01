# HuiAgent MCP Server

HuiAgent Desktop 的 MCP 服务进程（P0）：桌面截屏环形缓冲、平滑键鼠、Edge TTS 语音。

## 快速开始

```bash
cd hui-agent/repo/client/mcp-server
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 终端 1：Edge TTS
.venv/bin/python -m hui_mcp.voice.tts_proxy

# 终端 2：测试 TTS
.venv/bin/python -c "
from hui_mcp.voice.tts_client import TtsClient
r = TtsClient().synthesize('你好，我是 HuiAgent 助手。')
print('mp3 bytes', len(r.audio), 'voice', r.voice)
"

# MCP stdio（供 Cursor 连接）
.venv/bin/python -m hui_mcp
```

或使用一键脚本：

```bash
./scripts/start-dev.sh
```

## Cursor MCP 配置

```json
{
  "mcpServers": {
    "hui-agent-desktop": {
      "command": "/ABS/PATH/hui-agent/repo/client/mcp-server/.venv/bin/python",
      "args": ["-m", "hui_mcp"],
      "env": {
        "TTS_PROXY_PORT": "8896",
        "EDGE_TTS_VOICE": "zh-CN-XiaoxiaoNeural"
      }
    }
  }
}
```

## 配置

首次运行写入 `~/.hui-agent/config.json`（Socket token、TTS 参数等）。

## 文档

- [PRD](../../docs/prd/desktop-mcp-client.md)
- [技术方案](../../docs/solution/desktop-mcp-client.md)
- [Edge TTS 集成](../../docs/solution/edge-tts-integration.md)
