# HuiAgent: 桌面 AI 伴侣与 Cursor MCP 协同架构

> **Technical Paper v1.0** · 2026-08-01  
> **作者**：HuiAgent Team / jsCanvas  
> **English version**: [PAPER.en.md](./PAPER.en.md)  
> **代码仓库**：[https://github.com/jsCanvas/hui-agent](https://github.com/jsCanvas/hui-agent)  
> **项目官网**：[https://jscanvas.github.io/hui-agent/](https://jscanvas.github.io/hui-agent/)（GitHub Pages）

---

## 摘要（Abstract）

HuiAgent 是一套面向知识工作者的**本地桌面 AI 伴侣**系统。它将透明浮层 UI（Companion）、Python Daemon、Model Context Protocol（MCP）工具链与 Cursor IDE Agent 通过 Socket 长连接耦合，实现「观察屏幕 → 理解文档 → 操作键鼠 → 中文语音反馈」的闭环。Companion 输入区支持**工作区选择、图片上传、`@` 引用项目文件、屏幕画笔标注**，任务可携带文件与图片上下文供 Cursor **vibe coding**。本文介绍其分层架构、双工语音（Duplex）边缘响应、Cursor Socket Relay 任务模型，以及以读屏滚页替代后台 OCR 的主动阅读工作流。系统已在 macOS 上验证飞书文档语音阅读、Companion PTT 通话等场景。

**关键词**：桌面自动化、MCP、Cursor Agent、语音双工、屏幕理解、本地 Daemon

---

## 1. 引言

大模型 Agent 在 IDE 内已能高效辅助编程，但用户大量工作发生在浏览器、文档与协作工具中。云端 Agent 无法直接访问本机屏幕与输入设备；传统 RPA 缺乏语义理解与对话式交互。HuiAgent 的定位是 **hui-agent 平台的本地代理**：在用户桌面提供标准 MCP 接口、最小侵入的 Companion 浮层，并与 Cursor 等 MCP Host 对接，使「AI 大脑在 IDE、眼睛和手脚在 OS」成为可部署架构。

**贡献概览**：

1. **Companion + Daemon + MCP** 三层分离，Companion 仅作入口与 TTS/STT 展示，复杂推理交给 Cursor。
2. **Socket Relay（`:18765`）** 使 Companion 任务以 NDJSON 长连接阻塞等待 Cursor 完成，避免频繁切前台。
3. **Duplex 双工**：本地边缘层即时 ack 与简单工具执行，Cursor 异步接管完整规划。
4. **主动读屏工作流**：`get_screenshot` + 视觉理解 + 小步 `mouse_scroll`，替代默认后台 OCR Worker。
5. **Companion 任务输入增强**：工作区绑定、`@` 提及文件/图片、屏幕画笔标注，任务文本自动附加 `[工作区文件]` / `[用户上传图片]` 上下文。

---

## 2. 相关工作

| 方向 | 代表方案 | 与 HuiAgent 差异 |
|------|----------|------------------|
| IDE Agent | Cursor, Copilot | 侧重代码库，弱桌面 UI |
| MCP | Anthropic MCP 规范 | HuiAgent 提供桌面 Host 侧实现 |
| RPA | UiPath, AutoHotkey | 规则驱动，无统一 LLM 工具协议 |
| 语音助手 | Siri, 智能音箱 | 无文档读屏与 IDE 协同 |

HuiAgent 填补 **MCP 桌面工具 Host + 轻量 Companion UI + Cursor 大脑** 的空白。

---

## 3. 系统架构

```
┌──────────────────┐   WebSocket/NDJSON    ┌─────────────────────┐
│ Companion (Tauri)│ ◄──────────────────► │ Daemon (Python)      │
│ React · VRM/TTS  │                       │ Capture · TTS · STT  │
└────────┬─────────┘                       │ Socket Bridge :18765 │
         │                                   └──────────┬──────────┘
         │ invoke                                      │
         ▼                                               │ role=cursor
┌──────────────────┐         MCP stdio         ┌─────────▼──────────┐
│ 设置 · 托盘      │                           │ cursor-socket-client│
└──────────────────┘                           └─────────┬──────────┘
                                                           │
                                              ┌────────────▼────────────┐
                                              │ Cursor Agent + MCP      │
                                              │ 22+ tools: screenshot,  │
                                              │ mouse_*, keyboard_*,    │
                                              │ companion_speak, …      │
                                              └─────────────────────────┘
```

### 3.1 Companion 浮层

- 右下角透明窗口：数字人肖像、PTT/文字输入、状态 overlay（监听中 / 执行中）。
- 不展示长聊天日志；进度通过状态与 TTS 反馈。
- Tauri 2 壳管理子进程、系统托盘、Socket 事件转发。

### 3.2 Companion 任务输入与屏幕标注

输入栏上方为**工作区与附件工具条**：

| 能力 | 说明 |
|------|------|
| **选择工作区** | 绑定 Cursor 项目目录，写入 `~/.hui-agent/config.json` 的 `cursor.workspace` |
| **上传图片** | 多选导入至 `{workspace}/.hui-agent/uploads/`；icon 角标显示数量；悬停可预览列表并删除 |
| **`@` 提及** | 输入 `@` 弹出工作区文件与已上传图片；选中后插入 `@path` / `@filename` |
| **画笔 / 橡皮擦** | 全屏透明 overlay 在页面上画线标注；橡皮擦清除；`Esc` 或再次点画笔退出 |
| **窗口层级** | Companion 保持 `alwaysOnTop`，始终浮于画板 overlay 之上 |

发送任务时，Rust → Daemon → `runtime._compose_task_text` 解析 `@` 引用，合并 `file_paths` 与 `image_paths`，并在任务正文附加：

```
[工作区文件: /abs/path/to/file.ts]
[用户上传图片: /abs/path/to/photo.png]

请结合以上 @ 引用的工作区文件与图片，在当前项目上下文中分析并协助 vibe coding。
```

工作区文件列表由 Tauri 命令 `list_workspace_mention_files` 在本地遍历（忽略 `.git`、`node_modules` 等目录）。

### 3.3 Daemon 与 Socket Bridge

- **Health**：`http://127.0.0.1:18766/health`
- **帧缓冲**：10fps 环形缓冲供 `get_recent_frames`
- **Relay**：`cursor_relay.py` 维护 pending 任务，等待 `companion_task_complete`
- **Voice**：`/voice/*` HTTP + Socket 事件 `voice.stt.final`

### 3.4 MCP 工具集

核心工具包括：`get_screenshot`、`get_screen_info`、`mouse_move`、`mouse_click`、`mouse_scroll`、`keyboard_*`、`activate_document_app`、`companion_speak`、`companion_task_pending`、`companion_task_complete`、`companion_socket_connect_and_wait` 等。

自动化操作可配置 `automation.require_consent`；开发模式可关闭 Companion 确认弹窗。

---

## 4. Cursor Socket Relay 任务模型

### 4.1 连接与监听

1. Agent 调用 `companion_socket_connect_and_wait`（或脚本 `connect-cursor-socket.sh`）。
2. 后台进程 `cursor-socket-client.py` 以 `role=cursor` 连接 Bridge，默认监听 12 小时。
3. `wait_for_task` 轮询 Daemon pending，Companion 显示「监听中」。

### 4.2 任务闭环

```
wait → task_received → companion_task_pending
     → [读屏 / 键鼠 / speak]
     → companion_task_complete (auto_wait=true)
     → 自动 companion_socket_wait → 下一任务
```

`auto_wait` 在任务提交后于同一 MCP 调用内进入下一轮监听，减少 Agent 漏调 wait 的问题。

### 4.3 UI 策略

- **禁止** `activate_cursor_app` / `cmd+tab` 切前台（Relay 模式）。
- 文档聚焦：`mouse_move` + `mouse_click` 点击文档区（约宽 32%、高 42%）。
- 滚屏：`|dy| ≤ 24`，禁止 Page Down 连按。

---

## 5. 双工语音（Duplex）

用户 PTT 输入经 STT 变为文本后：

| 层级 | 延迟 | 行为 |
|------|------|------|
| **边缘（builtin/GGUF）** | 百 ms 级 | 即时 ack TTS、可选 `get_screenshot` 等简单动作 |
| **Cursor** | 秒～分钟级 | 完整规划、多屏阅读、`companion_speak` 分段播报 |

`voice_pending.duplex` 携带 `ack_text`、`executed_actions`、`defer_to_cursor: true`，Cursor follow-up 勿重复 ack。

---

## 6. 文档阅读工作流（Case Study）

**场景**：飞书 Wiki 英文小说，用户说「用中文阅读这篇小说」。

1. 边缘 ack 并首帧截屏。
2. Cursor `mouse_scroll` 小步下滚，多次 `get_screenshot` 理解简介与正文边界。
3. `companion_speak` 分段中文口播摘要。
4. `companion_task_complete` 提交 Markdown 摘要并 `auto_wait` 继续监听。

该流程不依赖 `companion_doc_read_start` 后台 OCR，降低与前台文档状态不一致的风险。

---

## 7. 实现与部署

- **客户端路径**：`repo/client/`（Tauri + React + Python MCP）
- **依赖**：Rust、Node 20+、Python 3.12；macOS 需屏幕录制与辅助功能
- **配置**：`~/.hui-agent/config.json`（TTS/STT/agent/automation/doc_read）
- **启动**：`npm run dev`

详细安装与权限说明见 [官网使用指导](https://jscanvas.github.io/hui-agent/#guide) 与 [Companion 使用说明](../docs/prd/companion-usage.md)。

---

## 8. 讨论与限制

| 项 | 说明 |
|----|------|
| 平台 | 首期 macOS；Windows Tauri 可构建，输入层待充分测试 |
| MCP 阻塞 | `auto_wait` 长监听可能导致 MCP HTTP 超时；可设 `timeout_sec` 或 `auto_wait: false` |
| 画板 overlay | 标注层为普通窗口层级；Companion 置顶；全屏 App 上可能被系统遮挡 |
| 隐私 | 截屏与键鼠均在本机；Relay 不上传屏幕到 hui-agent 云端 |
| 模型 | 默认 Cursor 云端模型；可选本地 GGUF 仅用于边缘 outline/ack |

---

## 9. 结论

HuiAgent 展示了如何将 **MCP 桌面工具**、**Companion 轻 UI** 与 **Cursor Agent** 组合为可复现的桌面 AI 工作流。Socket Relay 与 Duplex 设计在保持 IDE 为「大脑」的同时，提供了语音入口与长时监听能力。我们开源完整客户端，并在官网提供演示动画与分步指导，供社区扩展与集成。

---

## 参考文献与链接

1. Anthropic. *Model Context Protocol*. [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
2. Cursor. *Cursor IDE Documentation*. [https://cursor.com/docs](https://cursor.com/docs)
3. **HuiAgent 源码**：[https://github.com/jsCanvas/hui-agent](https://github.com/jsCanvas/hui-agent)
4. **HuiAgent 官网**：[https://jscanvas.github.io/hui-agent/](https://jscanvas.github.io/hui-agent/)
5. 项目内文档：`docs/prd/desktop-mcp-client.md`、`docs/solution/desktop-mcp-client.md`

---

## 附录 A：快速命令

```bash
git clone https://github.com/jsCanvas/hui-agent.git
cd hui-agent/repo/client && npm run dev
./scripts/connect-cursor-socket.sh
curl -sf http://127.0.0.1:18766/health | python3 -m json.tool
```

## 附录 B：版本信息

| 组件 | 版本 |
|------|------|
| MCP Server | 0.1.8 |
| Companion 输入增强 | v0.2（工作区 · @ 提及 · 图片 · 画笔） |
| 论文 | v1.1 |
| 日期 | 2026-08-01 |
