# HuiAgent Desktop Client

桌面端：**Tauri 2 壳** + **Python MCP 服务** + **Edge TTS** + **右下角 Companion 浮层**。

## 前置依赖

| 依赖 | 用途 |
|------|------|
| [Rust](https://rustup.rs/) | Tauri 编译 |
| Node.js 20+ | 前端 UI |
| Python 3.12 | MCP / TTS / Daemon |

## 首次安装

```bash
cd hui-agent/repo/client

# 1. Python MCP 服务
cd mcp-server
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ..

# 2. 前端 UI
cd ui && npm install && cd ..

# 3. Tauri CLI
npm install

# 4. 图标
python3 scripts/gen-icons.py
```

## 开发运行

```bash
cd hui-agent/repo/client
npm run dev          # tauri dev：Companion 浮层 + 托盘 + 后台服务
```

等价于自动：

- 启动 **Edge TTS Proxy** `127.0.0.1:8896`
- 启动 **Capture Daemon** `127.0.0.1:18766/health`（含 **Socket Bridge** `127.0.0.1:18765`）
- 显示右下角 **Companion**（聊天 + 📞 + Edge TTS 试听）
- 系统托盘：设置 / 重启服务 / 退出

仅 MCP（无 Tauri）：

```bash
./scripts/start-dev.sh
```

## 构建安装包

```bash
npm run build        # 产出 dmg/exe（需 Rust + 平台 SDK）
```

## 目录

```
client/
├── src-tauri/          # Rust：托盘、子进程、Tauri 命令
├── ui/                 # React：Companion + 设置页
├── mcp-server/         # Python MCP / TTS / Daemon
├── scripts/
└── package.json        # tauri dev/build
```

## Socket Bridge（Agent 实时连接）

Daemon 启动后监听 `127.0.0.1:18765`（NDJSON + Token 鉴权）。连接信息见设置页或：

```bash
cat ~/.hui-agent/config.json
python3 -m hui_mcp.socket_bridge   # 独立运行（调试）
```

Skill 文档：[hui-agent-socket-bridge/SKILL.md](../../docs/solution/skills/hui-agent-socket-bridge/SKILL.md)

### `chat.send` → Agent Runtime

Socket 客户端发送 `{"type":"chat.send","text":"..."}` 后，Bridge 调用 **Agent Runtime**：

- 已配置 `llm.api_key` 时：**LLM Agent**（OpenAI 兼容 API）
- 默认 **Cursor Relay**：Companion → Socket 长连接 → Cursor MCP（无 SDK）
- `agent.mode: rules` 时使用规则引擎

推送事件：

| 事件 | 说明 |
|------|------|
| `task.progress` | 步骤进度（plan / tool / scroll …） |
| `chat.delta` | 最终回复文本 |
| `chat.steps` | 步骤列表（可选） |
| `chat.done` | 任务结束 |

## Agent Runtime（Companion + HTTP）

Companion 浮层发送消息时，Tauri 调用 `POST http://127.0.0.1:18766/agent/chat`：

```json
{ "text": "阅读浏览器需求文档第三节" }
```

返回 `{ "ok", "reply", "steps", "task_id", "data" }`，UI 展示回复与步骤列表。

## Cursor Relay 模式（Companion → Socket → Cursor MCP）

默认 `agent.mode: cursor`。Companion 输入「完整阅读…并总结」时，**不启动 Cursor SDK**；任务经 Socket relay 交给当前 Cursor 会话中的 AI，由 MCP 读屏滚页并写摘要，结果回到 Companion。

### 使用步骤

1. 启动桌面端：`npm run dev`（仅启动 Daemon + Socket Bridge，**不会**自动连接 Cursor）
2. 在 **Cursor Agent** 中调用 **`companion_socket_connect`**（后台 detached 进程建连，**默认监听 12 小时**，**绝不**切 Cursor 前台）
3. 若 `continue_waiting: true`，循环调用 **`companion_socket_wait`** 直到 `task_received`
4. 收到任务后 **`companion_task_pending`** 处理；需切窗口时仅用 **mouse_move + mouse_click**，禁止 `activate_*`
5. **`companion_task_complete` 后** → 立即 **`companion_socket_wait`** 继续监听下一任务（**不要** disconnect）
6. 验证连接：`companion_connection_status` 或 `curl -sf http://127.0.0.1:18766/health`
7. **提前停止监听** → 手动调用 **`companion_socket_disconnect`**（12 小时到期后也会自动结束）
8. Socket 收到任务时：`cursor_trigger: notify_only`（默认）仅通知 + 剪贴板；设为 `background` 则自动提交后切回文档

`~/.hui-agent/config.json` 仅需：

```json
{ "agent": { "mode": "cursor" } }
```

- macOS：为 **Cursor** 与 **Python** 授予「屏幕录制」「辅助功能」
- 任务可能需数分钟，HTTP 超时已设为 600s

### Cursor IDE 内直接操控（可选）

`.cursor/mcp.json` 已配置同一 MCP；不经过 Companion 时，也可在 Cursor 聊天里直接调用桌面工具。

### 可选：OpenAI 兼容 LLM（`agent.mode: llm`）

显式配置 `llm.api_key` 时使用内置 LLM Agent，**默认不启用**。

### 文档阅读（Cursor Agent 主动读屏，默认）

Companion 发送「完整阅读第 X 节并总结」或「阅读 xxx.md 并总结」时：

1. **Cursor Agent**（默认）：`get_screenshot` → **Read 截图**理解 → `keyboard_press` / `mouse_scroll` 翻页 → 写摘要 → `companion_task_complete`
2. **禁止**长时间轮询 `companion_doc_read_status`；**禁止**默认启动后台 OCR Worker
3. 用户已在文档页前台时：仅用 `mouse_move` + `mouse_click` 聚焦，禁止 `activate_*` / `cmd+tab`
4. 需要搜索章节：`keyboard_hotkey` cmd+f → 粘贴关键词 → Enter → Esc

Legacy 后台 OCR Worker（可选，不推荐）：

```json
{ "doc_read": { "auto_start_on_relay": true } }
```

启用后仍可通过 `companion_doc_read_status` 轮询 `ocr_text` + `pages`。

查询 OCR 进度（仅 legacy Worker 模式）：

```bash
curl -sf "http://127.0.0.1:18766/agent/doc_read?task_id=YOUR_TASK_ID" | python3 -m json.tool
```

### 本地 GGUF 边缘模型（推荐）

一键安装 **Qwen2.5-0.5B-Instruct Q4**（约 400MB，纯本地，无需 api_key）：

```bash
cd hui-agent/repo/client
python3 scripts/setup-edge-gguf.py
```

脚本会：`pip install llama-cpp-python` → 下载 GGUF 到 `~/.hui-agent/models/` → 写入配置 `edge_model: auto`。

配置 `~/.hui-agent/config.json`：

```json
{
  "doc_read": {
    "enabled": true,
    "max_pages": 24,
    "stale_hits_to_stop": 2,
    "edge_outline": true,
    "edge_model": "auto",
    "gguf_model_path": "",
    "gguf_n_ctx": 4096,
    "gguf_n_threads": 0,
    "gguf_n_gpu_layers": 0,
    "gguf_max_tokens": 1024,
    "assume_doc_foreground": true,
    "auto_start_on_relay": false,
    "cursor_trigger": "notify_only"
  }
}
```

| `cursor_trigger` | Socket 收到任务后 |
|---|---|
| **`notify_only`（默认）** | 仅系统通知 + 剪贴板；需手动粘贴或 `companion_socket_wait` |
| `background` | osascript 自动提交后切回文档（短暂激活 Cursor） |
| `osascript` | 切换并保持 Cursor 前台（旧行为） |

Companion Socket 监听可配合项目 Hook：`.cursor/hooks.json`（`companion-task-stop.sh` stop hook 连续处理 pending）。

任务执行期间按 **Esc** 可立即终止（停止 OCR、结束 Relay 任务）。需在系统设置 → 隐私与安全性 → **辅助功能** 中允许 HuiAgent / Terminal。也可手动：`curl -X POST http://127.0.0.1:18766/agent/cancel -H 'Content-Type: application/json' -d '{"reason":"用户终止"}'`

| `edge_model` | 行为 |
|---|---|
| `auto` | 有 GGUF 则用本地小模型，否则规则引擎 |
| `gguf` | 强制 GGUF；失败时 fallback 规则引擎 |
| `builtin` | 仅规则结构化引擎（零依赖） |

手动安装依赖：`pip install -e mcp-server/[gguf]`

Apple Silicon 可设 `gguf_n_gpu_layers: 35` 启用 Metal 加速。

**不读取 `llm.api_key`**，与 Cursor 云端模型完全分离。`edge_outline` 仅供 Cursor 快速定位章节结构，**不能替代** Cursor 对 `ocr_text` 与 `pages` 截图的完整阅读。

OCR（推荐）：`brew install tesseract tesseract-lang`

### Socket 测试完整阅读

```b1ash
# 需先运行 cursor-socket-client.py，并在 Cursor 中 companion_task_complete
chmod +x scripts/socket-read-section.py
./scripts/socket-read-section.py "完整阅读物流服务文档第四节并总结"
```

等价于 Socket 发送：

```json
{"type":"chat.send","text":"完整阅读物流服务文档第四节并总结"}
```

会收到 `task.progress` → `chat.delta` → `chat.done`。

OCR（推荐，后台 Worker 依赖）：`brew install tesseract tesseract-lang`

## 语音通话（电话模式）

点击 Companion **☎ 电话** 进入通话模式：

1. **按住 PTT**（或自由说）→ Daemon **Google STT** 识别 → `voice.stt.final` 经 Socket 发给 Cursor
2. Cursor Agent 处理：`companion_speak` 分段播报 → `companion_task_complete channel=voice`
3. Companion 经 Socket 播放 TTS（3D VRM 口型/表情）；用户说话时可打断播报

**与文字任务相同的后台能力（电话模式不受影响）：**

| 能力 | 说明 |
|------|------|
| **Esc 终止** | 执行中按 **Esc** 终止当前 utterance（播报「已终止」并结束本轮）；需 **辅助功能** 权限 |
| **Socket 12h** | Cursor 侧 `companion_socket_connect` → 循环 `companion_socket_wait`；**不要** `companion_socket_disconnect` |
| **完成后** | `companion_task_complete` 返回 `agent_next=companion_socket_wait`，继续监听下一句话 |

Daemon 端点：

| 路径 | 说明 |
|------|------|
| `POST /voice/start` | 开启通话（Companion 传 `background_listen: false`） |
| `POST /voice/stop` | 结束通话 |
| `POST /voice/utterance` | `{text, speak?}` 语音任务 + 可选 TTS |
| `POST /voice/tts/stop` | 停止当前播报 |

Socket：`voice.start` / `voice.stop`；事件 `voice.stt.final`、`voice.tts.start/end`。

MCP 工具：`stt_listen`（`stt.engine=google` 时需 SpeechRecognition+PyAudio）、`voice_call_start/stop`。

**Companion 桌面端 STT**：Tauri/WKWebView 不支持 Web Speech API（会报 `service-not-allowed`），电话模式改走 Daemon 麦克风识别（Google STT）。首次需：

```bash
brew install portaudio
cd mcp-server && .venv/bin/pip install SpeechRecognition PyAudio
```

并在 **系统设置 → 隐私与安全性 → 麦克风** 中允许 HuiAgent。

默认 `~/.hui-agent/config.json` → `"stt": {"engine": "web", "input_mode": "push_to_talk"}`（浏览器调试仍用 Web Speech；桌面 Companion 自动用后端 STT）。

**Push-to-talk（按住说）**：默认模式，按住 Companion 按钮或 **Space** 才开启麦克风，松开即识别发送，减少误触发。可切换为「自由说」连续识别。

纯 Socket 客户端可设 `"engine": "google"`。

## Companion 3D 数字人（VRM，默认）

默认使用 **Three.js + @pixiv/three-vrm** 渲染国漫风 3D 形象，TTS 口型与 Companion 状态联动：

- 模型：`ui/public/vrm/companion.vrm`（CC0 **MoonGirl**，[100Avatars R2](https://opensourceavatars.com) / Arweave）
- 组件：`AvatarVRM` + `vrmDialogue.ts`（`aa/oh` 口型、happy/surprised 等表情、头部 idle 动画）
- 降级：VRM 加载失败 → Canvas 卡通；`VITE_USE_LIVE2D=true` 时优先 Live2D

**下载/更新模型**：

```bash
chmod +x scripts/fetch-vrm-avatar.sh
./scripts/fetch-vrm-avatar.sh
# 或指定 URL：./scripts/fetch-vrm-avatar.sh "https://arweave.net/..."
```

环境变量：

| 变量 | 说明 |
|------|------|
| `VITE_VRM_MODEL_URL` | 本地 VRM 路径（默认 `/vrm/companion.vrm`） |
| `VITE_VRM_MODEL_CDN` | 离线失败时的 Arweave 回退 URL |
| `VITE_USE_VRM=false` | 禁用 3D，改用 Canvas 卡通 |
| `VITE_USE_LIVE2D=true` | 优先 Live2D |

## 序列帧肖像（可选，实验性）

预渲染视频序列帧方案仍保留在 `ui/public/avatar/`，需改 `CompanionAvatar` 或设自定义渲染路径后使用：

```bash
./scripts/avatar-video-to-frames.sh talk.mp4 ui/public/avatar/seq/speaking 12
cd mcp-server && .venv/bin/python ../scripts/generate-avatar-videos.py
```

## Live2D 数字人（可选）

设置 `VITE_USE_LIVE2D=true` 时使用 **Live2D Cubism 4**（`pixi-live2d-display` + Haru 示例模型）：

- TTS 在 **WebView 内播放**（Edge TTS HTTP → Web Audio Analyser → `ParamMouthOpenY`）
- Live2D 加载失败时自动降级为 3D VRM → Canvas

离线资源（可选，避免运行时 CDN）：

```bash
chmod +x scripts/fetch-live2d-assets.sh
./scripts/fetch-live2d-assets.sh
```

## Cursor MCP

设置页 → **复制 Cursor MCP 配置**，或手动：

```json
{
  "mcpServers": {
    "hui-agent-desktop": {
      "command": "/ABS/PATH/client/mcp-server/.venv/bin/python",
      "args": ["-m", "hui_mcp"]
    }
  }
}
```

## 文档

- [PRD](../../docs/prd/desktop-mcp-client.md)
- [技术方案](../../docs/solution/desktop-mcp-client.md)
