# HuiAgent

**HuiAgent Desktop** — 本地桌面 AI 伴侣：Companion 浮层 + MCP 读屏键鼠 + Cursor Socket Relay 双工语音。

| 资源 | 链接 |
|------|------|
| **介绍官网** | [website/](website/) · 部署后 [GitHub Pages](https://jscanvas.github.io/hui-agent/) |
| **技术论文** | [paper/PAPER.md](paper/PAPER.md) |
| **客户端文档** | [repo/client/README.md](repo/client/README.md) |
| **Companion 指南** | [docs/prd/companion-usage.md](docs/prd/companion-usage.md) |

## 快速开始

```bash
git clone https://github.com/jsCanvas/hui-agent.git
cd hui-agent/repo/client

# Python MCP
cd mcp-server && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && cd ..

# UI + Tauri
cd ui && npm install && cd ..
npm install

npm run dev
```

在 Cursor 中说 **「连接 socket」** 或调用 MCP `companion_socket_connect_and_wait`，即可进入 Companion 语音/阅读任务监听。

## 架构概览

```
Companion（浮层 UI + TTS/STT）
    ↕ Socket :18765
Daemon（截屏、Relay、Voice）
    ↕ MCP stdio
Cursor Agent（大脑：读截图、规划、摘要）
    ↕ MCP 工具
鼠标 / 键盘 / 滚屏 / 激活文档
```

## 目录

```
hui-agent/
├── repo/client/     # Tauri 桌面端 + Python MCP + Companion UI
├── docs/            # PRD / 技术方案
├── website/         # 介绍官网（静态页，可 GitHub Pages 部署）
├── paper/           # 项目论文 / 白皮书
└── docker/          # 容器相关（可选）
```

## License

MIT — see [LICENSE](LICENSE) if present.
