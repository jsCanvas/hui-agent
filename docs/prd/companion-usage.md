# Companion 使用说明

> 文档版本：v1.0  
> 日期：2026-07-26  
> 所属项目：hui-agent / repo/client  
> 关联文档：[桌面端 PRD](./desktop-mcp-client.md) · [技术方案](../solution/desktop-mcp-client.md) · [Client README](../../repo/client/README.md)  
> 状态：使用指南

---

## 1. Companion 是什么

**Companion** 是 HuiAgent Desktop 右下角的透明浮层助手，由 **数字人表情 + 单行输入框 + 小图标** 组成，占用屏幕空间极小。

| 角色 | 职责 |
|------|------|
| **Companion** | 任务入口、Live2D 状态展示、语音通话 UI |
| **Cursor AI（MCP）** | 大脑：读截图、理解文档、写摘要、决策 |
| **MCP 工具** | 手脚：截屏、鼠标、键盘、滚轮 |
| **Daemon + Socket** | 后台：relay 任务、阻塞等待 Cursor 完成 |

Companion **不展示**聊天日志、步骤列表或任务摘要文字；任务完成后仅通过 **Live2D 状态变化**（等待 → 执行中 → 完成 → 休息）反馈进度。

---

## 2. 启动前准备

### 2.1 系统权限（macOS）

为以下程序授予 **屏幕录制** 与 **辅助功能**：

- **Cursor**（MCP 读屏、键鼠）
- **Python** / **HuiAgent**（Daemon 截屏、cliclick 输入）

### 2.2 启动桌面端

```bash
cd hui-agent/repo/client
npm run dev
```

自动拉起：

| 服务 | 地址 |
|------|------|
| Companion 浮层 | 右下角透明窗口 |
| Capture Daemon | `http://127.0.0.1:18766/health` |
| Socket Bridge | `127.0.0.1:18765` |
| Edge TTS Proxy | `http://127.0.0.1:8896/health` |

### 2.3 Cursor 侧（默认 Cursor Relay 模式）

1. **MCP 配置**（项目 `.cursor/mcp.json` 或用户级配置）：

```json
{
  "mcpServers": {
    "hui-agent-desktop": {
      "command": "/ABS/PATH/hui-agent/repo/client/mcp-server/.venv/bin/python",
      "args": ["-m", "hui_mcp"],
      "env": {
        "TTS_PROXY_PORT": "8896",
        "EDGE_TTS_VOICE": "zh-CN-XiaoxiaoNeural",
        "HUI_MCP_VERSION": "0.1.1"
      }
    }
  }
}
```

2. Cursor Settings → MCP → **`hui-agent-desktop`** 开启，确认 **22 tools**（含 `activate_document_app`、`companion_speak`）。

3. **Socket 长连接**（单独终端保持运行）：

```bash
cd hui-agent/repo/client
python3 scripts/cursor-socket-client.py
```

看到 `✓ Cursor relay connected` 即表示 `cursor_online: true`。

### 2.4 Agent 模式

`~/.hui-agent/config.json` 默认：

```json
{
  "agent": { "mode": "cursor" }
}
```

---

## 3. 界面说明

```
        ┌─────────┐
        │ Live2D  │  ← 拖拽此处可移动整个浮层
        │  表情   │
        └─────────┘
   [ PTT ] [ ∞ ] [ 🎤 ]   ← 仅通话模式显示
┌──────────────────────────┐
│ ☎ │ 输入框…          │ ↑ │
└──────────────────────────┘
 电话  文字任务            发送
```

| 元素 | 操作 |
|------|------|
| **表情区域** | 按住拖拽 → 移动浮层位置（位置会记住） |
| **☎ 电话** | 进入/退出语音通话模式 |
| **输入框** | 输入任务，Enter 或 ↑ 发送 |
| **↑ 发送** | 提交文字任务 |
| **PTT / ∞ / 🎤** | 通话模式：按住说 / 自由说 / 麦克风按钮 |

窗口特性：透明背景、始终置顶、无标题栏，默认停靠主屏右下角。

---

## 4. 文字任务（Cursor Relay）

### 4.1 典型流程

1. 在浏览器或文档 App 中打开要阅读的内容（如飞书文档）。
2. 在 Companion 输入框发送任务，例如：

   > 完整阅读物流服务文档第四节并总结

3. Live2D 状态变化：**休息 → 等待 → 执行中 → 完成 → 休息**。
4. **双工架构**（文档阅读任务）：
   - Daemon **后台 Worker**：滚屏 + OCR + 本地 GGUF 生成 `edge_outline`（**仅辅助索引**）
   - Cursor AI：`companion_doc_read_status` 取 `ocr_text` + `pages` 截图 → **逐张读图** + 对照 OCR → 写摘要
   - **禁止** Cursor 仅依据 `edge_outline` 提交摘要；流程图/UI 须视觉理解
   - `companion_task_complete` 提交结果

用户可在 Cursor 聊天中看到处理过程；Companion 侧 **不显示**摘要文字。

### 4.2 架构示意

```
Companion 输入
    → POST /agent/chat（Daemon）
    → CursorRelay 阻塞
    → 并行：DocReadWorker（滚屏+OCR，后台线程）
    → Socket task.request → cursor-socket-client
    → Cursor AI：doc_read_status → 读 pages 截图 + ocr_text → 摘要（edge_outline 仅参考）
    → companion_task_complete
    → Relay 解锁，Companion 状态「完成」
```

### 4.3 使用注意

- 发送任务前确保 **Socket 客户端已连接**，否则提示 Cursor 未连接。
- 同时只处理 **一个** pending 任务；进行中请勿重复发送。
- 任务可能耗时数分钟（读长文档），HTTP 超时 600s。
- 滚屏在 **后台 Worker** 执行；Cursor 须读 `pages` 截图 + 完整 `ocr_text`，不可只读 `edge_outline`。
- 需安装 Tesseract：`brew install tesseract tesseract-lang`

---

## 5. 语音通话模式

### 5.1 进入/退出

- 点击 **☎** 进入通话；图标变为 **✕**，再次点击挂断。
- 进入后 Live2D 进入 **对话** 状态。

### 5.2 输入方式

| 模式 | 说明 |
|------|------|
| **PTT（按住说）** | 按住 🎤 或 Space 说话，松手结束 |
| **自由说（∞）** | 持续监听，识别到一句后自动派发 |

### 5.3 语音链路（Socket 双向）

```
用户说话（Web Speech API）
    → Companion Socket（role=companion）
    → voice.stt.final / voice.stt.partial
    → Cursor Socket（voice.user.message）
    → Cursor AI（MCP 大脑）
    → companion_speak（Socket voice.speak → Companion TTS + 口型）
    → companion_task_complete（channel=voice, utterance_id）
    → voice.turn.done → Live2D 回到对话
```

要点：

- **非阻塞**：每句 utterance 立即 ack，不等待 600s HTTP；可多轮排队。
- **Cursor 指挥播报**：用 MCP **`companion_speak`**（非 `tts_speak`），Companion 侧 Edge TTS + Live2D 口型。
- **partial STT**：识别过程中 `voice.stt.partial` 经 Socket 发给 Cursor（可用于打断/上下文）。
- Companion App 启动时自动连接 Socket（`companion_socket`）；需 **`cursor-socket-client.py`** 与 Daemon 同时在线。

用户说话时会 **自动打断** 当前 TTS。通话模式下也可在输入框 **打字发送**（同样走 voice relay）。

### 5.4 Cursor 处理通话的典型步骤

1. `companion_task_pending` → 查看 `voice_pending.utterance_id` + 用户原文
2. 按需 MCP 读屏/操作
3. `companion_speak({text: "…", final: false})` 可多次分段播报
4. `companion_task_complete({channel: "voice", utterance_id, reply: "…"})` 结束本轮

---

## 6. Live2D 状态说明

| 状态 | 含义 | 何时出现 |
|------|------|----------|
| **休息** | 空闲 | 默认、任务结束后 |
| **等待** | 任务已提交，等待 Cursor | 发送后瞬间 |
| **执行中** | Cursor 正在读屏/操作 | Relay 处理中 |
| **完成** | 任务成功结束 | 约 1.8s 后回到休息/对话 |
| **对话** | 通话模式空闲 | 电话模式未执行任务时 |
| **聆听** | 正在识别语音 | 通话 + STT 激活 |
| **播报** | TTS 播放中 | 通话模式回复播报 |

状态通过表情/姿态体现，**无文字徽章**（无障碍 `aria-label` 仍保留）。

---

## 7. 系统托盘

菜单栏 HuiAgent 图标：

| 菜单项 | 作用 |
|--------|------|
| 打开设置 | 服务状态、Cursor 配置导出 |
| 显示助手 | 显示 Companion 窗口 |
| 重启服务 | 重启 TTS + Daemon |
| 退出 | 关闭应用 |

关闭 Companion 窗口（×）时 **仅隐藏**，不退出应用；可从托盘再次显示。

---

## 8. 常见问题

### 8.1 Cursor 不执行任务

| 检查项 | 方法 |
|--------|------|
| Socket 是否在线 | `curl -s http://127.0.0.1:18766/health` → `cursor_online: true` |
| Socket 客户端 | 终端运行 `cursor-socket-client.py` |
| MCP 是否最新 | Settings → MCP 显示 **22 tools**，含 `companion_speak` |
| Pending 任务 | `curl -s http://127.0.0.1:18766/agent/pending` |

若 MCP 重启后仍显示 20 tools，为 **Cursor 工具缓存** 问题：

1. Cmd+Shift+P → **Reload Window**
2. 或删除缓存：`rm -rf ~/.cursor/projects/<项目>/mcps/project-0-task-hui-agent-desktop/tools`
3. 重新开启 `hui-agent-desktop` MCP

### 8.2 鼠标移动了但页面不滚

- 确认 MCP 已更新（`mouse_scroll` 使用 macOS 原生滚轮，非 Page Down）。
- 任务执行前需 **`mouse_click` 文档区域** 获取焦点，再 `mouse_scroll(dy=-24)`。

### 8.3 Live2D 显示为粉色圆球

- Live2D 模型未加载，使用 Fallback 表情；检查 `/live2d/` 静态资源与网络。
- 不影响任务派发，仅视觉降级。

### 8.4 任务超时

- 确认 Cursor 中 AI 已响应 follow-up 并调用 `companion_task_complete`。
- 长文档需多屏滚屏，可适当延长等待或缩小单次阅读范围。

---

## 9. 配置参考

`~/.hui-agent/config.json` 常用字段：

```json
{
  "agent": { "mode": "cursor" },
  "socket": {
    "host": "127.0.0.1",
    "port": 18765,
    "token": "..."
  },
  "stt": {
    "engine": "web",
    "input_mode": "push_to_talk"
  },
  "tts": {
    "voice": "zh-CN-XiaoxiaoNeural"
  }
}
```

Companion 窗口位置保存在浏览器 `localStorage`（`hui-agent.companion-position`）。

---

## 10. 相关命令速查

```bash
# 开发
cd hui-agent/repo/client && npm run dev

# Socket relay（Cursor 终端常开）
python3 scripts/cursor-socket-client.py

# 健康检查
curl -s http://127.0.0.1:18766/health | python3 -m json.tool
curl -s http://127.0.0.1:18766/agent/pending | python3 -m json.tool

# MCP 工具数验证（应输出 21）
cd mcp-server && .venv/bin/python -c \
  "from hui_mcp.tools.schemas import TOOLS; print(len(TOOLS))"
```

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-07-26 | 首版：Companion 启动、UI、Cursor Relay、通话、排障 |
