# 桌面端 MCP 客户端技术方案

> 文档版本：v1.2  
> 日期：2026-07-26  
> 所属项目：hui-agent / repo/client  
> 关联 PRD：[desktop-mcp-client.md](../prd/desktop-mcp-client.md) · [Edge TTS 集成](./edge-tts-integration.md)  
> 状态：方案评审

---

## 1. 背景与目标

### 1.1 背景

hui-agent 是「智能桌面终端」平台，采用单容器多进程架构运行 backend / web 服务，**桌面端 client 独立部署、不写入 Docker 镜像**。智能体需要具备「看屏幕 → 理解界面 → 操作键鼠」的闭环能力，因此桌面端必须在本机启动 MCP（Model Context Protocol）服务，向 Cursor、Claude Desktop 或 hui-agent 云端智能体暴露标准化工具接口。

### 1.2 目标

开发一款跨平台桌面应用（**macOS + Windows**），用户打开应用后自动启动 MCP 服务，提供以下能力：

| 能力 | 规格 | 用途 |
|------|------|------|
| 桌面画面采集 | 最近 **5 秒**、**10 fps** 的逐帧截图（共 50 帧），写入临时目录 | 智能体理解近期交互与界面变化 |
| 鼠标操作 | 移动、点击、拖拽、滚轮；**连贯平滑移动**，禁止坐标瞬移 | 模拟人类操作轨迹 |
| 键盘操作 | 单键、组合键、文本输入 | 表单填写、快捷键、导航 |
| **桌面助手浮层** | 右下角聊天框 + 青年女性数字人 | 自然语言任务派发与反馈 |
| **Socket 实时桥接** | `127.0.0.1:18765` JSON 协议 | 智能体低延迟双向交互 |
| **语音通话** | TTS 播报 + STT 识别 | 电话模式口语沟通与进度播报 |

### 1.3 非目标（本期不做）

- Linux 桌面支持
- 多显示器独立 MCP 实例（首期统一主屏）
- 硬件 HID 后端（可参考 sibling 项目 mousekey，后续扩展）
- 云端远程桌面中继（VNC/RTC）
- 3D 超写实数字人（首期 2D/Live2D）
- 离线 TTS 作为 Edge 不可用时的降级（piper，P2）

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        桌面端应用 (repo/client)                           │
│  ┌─────────────┐  ┌──────────────────────┐  ┌────────────────────────┐ │
│  │ Tauri Shell │  │ Companion Overlay    │  │ Agent Runtime (内置)   │ │
│  │ 托盘/设置    │  │ 聊天框+数字人+📞电话  │  │ 任务编排→MCP/Socket    │ │
│  └──────┬──────┘  └──────────┬───────────┘  └───────────┬────────────┘ │
│         │ spawn               │ IPC                       │ in-proc      │
│         ▼                     ▼                           ▼              │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    MCP Server + Socket Bridge                        │ │
│  │  FrameBuffer │ InputDriver │ Voice(TTS/STT) │ Tools │ Socket :18765 │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ stdio MCP / Socket JSON / HTTP(可选)
                                ▼
              ┌─────────────────────────────────────────────────┐
              │ Cursor / Claude / hui-agent backend / Skill Agent│
              └─────────────────────────────────────────────────┘
```

### 2.1 进程模型

1. **Tauri 主进程**：窗口/托盘、Companion 浮层、权限、子进程生命周期。
2. **Companion Overlay 窗口**：透明置顶 WebView，聊天 UI + Live2D/Spine 数字人。
3. **Agent Runtime**（内置或连接 hui-agent backend）：解析用户意图，编排 MCP Tool 调用链。
4. **MCP Server 子进程**：stdio MCP + **Socket Bridge** + Voice 模块；stdout 仅 JSON-RPC。
5. **CaptureThread**：10 Hz 截屏环形缓冲；Socket 可订阅 `frame.push`。

### 2.2 与 hui-agent 生态的关系

```
hui-agent/
├── repo/
│   ├── client/          ← 本方案实现位置（桌面端 + MCP）
│   ├── backend/         ← 可通过 HTTP MCP 或 WebSocket 桥接调用 client
│   └── web/             ← 管理界面，展示 client 在线状态
├── docs/
│   └── solution/        ← 本文档
└── Dockerfile           ← 不含 client；client 在用户本机运行
```

---

## 3. 技术选型

### 3.1 方案对比

| 维度 | 方案 A：Tauri + Python MCP | 方案 B：Electron + Node MCP | 方案 C：纯 Python 托盘 |
|------|---------------------------|------------------------------|-------------------------|
| 安装包体积 | ~15–25 MB | ~80–150 MB | ~30 MB（含 Python 运行时） |
| 跨平台 | ✅ macOS / Windows | ✅ | ✅ |
| 权限 UX | Rust 原生对话框 + Web 引导 | 类似 | 较弱 |
| 复用 mousekey | ✅ 直接复用 capture/humanize | 需重写 | ✅ |
| MCP SDK 成熟度 | Python `mcp` 官方 SDK | `@modelcontextprotocol/sdk` | 同左 |
| 推荐度 | **★★★ 推荐** | ★★ | ★★ |

### 3.2 推荐栈（方案 A）

| 层级 | 技术 | 说明 |
|------|------|------|
| 桌面壳 | **Tauri 2** | 轻量、Rust 侧管理子进程与系统 API |
| UI | React / Vue + Tailwind | 设置页、权限状态、MCP 端口 |
| MCP 服务 | **Python 3.12 + `mcp` SDK** | stdio 为主，可选 Streamable HTTP |
| 截屏 | **mss** | 跨平台、高性能；macOS Retina 需处理 scale |
| 鼠标/键盘 (macOS) | **cliclick** + 自研贝塞尔路径 | 已在 mousekey 验证 |
| 鼠标/键盘 (Windows) | **SendInput** via `pyautogui` 或 `pynput` + 自研路径插值 | 统一 InputDriver 接口 |
| 临时帧目录 | `tempfile` + 环形覆盖 | 见 §4 |

> **选型理由**：hui-agent 同仓库已有 mousekey 项目的 capture / humanize 实现，Python MCP 可最大化复用；Tauri 提供比 Electron 更小的分发体积和更可靠的子进程管理。

---

## 4. 核心模块设计

### 4.1 帧缓冲与临时目录（能力 1）

#### 4.1.1 需求参数

- 缓冲时长：**5 秒**
- 采样率：**10 fps**
- 缓冲容量：**50 帧**
- 格式：**PNG**（无损，便于 OCR/VLM；体积可接受：1080p 单帧 ~200KB，50 帧 ~10MB 峰值）

#### 4.1.2 环形缓冲设计

```python
@dataclass
class FrameSlot:
    index: int           # 0..49 单调递增
    timestamp_ms: int    # Unix ms
    filepath: Path       # 临时 PNG 路径

class FrameRingBuffer:
    capacity: int = 50

    def push(self, image: ndarray) -> FrameSlot: ...
    def snapshot_last_n_seconds(self, seconds: float = 5.0) -> list[FrameSlot]: ...
    def materialize_to_dir(self, dest: Path | None = None) -> Path:
        """复制/链接最近 50 帧到独立临时目录，返回目录路径供 MCP Resource 读取"""
```

#### 4.1.3 采集线程

```
启动 MCP 服务
    │
    ▼
spawn CaptureThread (daemon)
    │  loop every 100ms:
    │    grab = mss.grab(primary_monitor)
    │    encode PNG → overwrite ring[slot % 50]
    │    slot.index++, slot.timestamp = now()
    ▼
MCP tool: get_recent_frames
    │
    ▼
materialize_to_dir() → /tmp/hui-agent-frames-{uuid}/
    │  frame_000042_1719305123456.png
    │  frame_000043_1719305123567.png
    │  ...
    │  manifest.json   # 元数据：fps、分辨率、monitor、scale
    ▼
返回目录路径 + manifest（或通过 MCP Resource URI 暴露）
```

#### 4.1.4 manifest.json 结构

```json
{
  "version": 1,
  "captured_at_ms": 1719305128000,
  "duration_sec": 5.0,
  "fps": 10,
  "frame_count": 50,
  "monitor": { "id": 0, "width": 1920, "height": 1080, "scale_factor": 2.0 },
  "frames": [
    { "file": "frame_000042_1719305123456.png", "index": 42, "timestamp_ms": 1719305123456 },
    "..."
  ]
}
```

#### 4.1.5 MCP 暴露方式

| 方式 | 用途 |
|------|------|
| **Tool: `get_recent_frames`** | 物化临时目录，返回路径与 manifest |
| **Resource: `frame://latest`** | 返回最新单帧（快速预览） |
| **Resource: `frames://recent`** | 返回 manifest + 批量 URI 列表 |

临时目录清理策略：

- 每次 `get_recent_frames` 创建新目录，**TTL 10 分钟**后后台删除；
- 环形缓冲内部文件固定 50 个，原地覆盖，不膨胀。

#### 4.1.6 多显示器与 Retina

- 首期：**主显示器**（`monitors[1]` in mss）。
- macOS Retina：`grab` 返回物理像素，manifest 记录 `scale_factor`；鼠标坐标统一为**逻辑点坐标**（与 cliclick 一致），提供 `px_to_global` / `global_to_px` 换算（复用 mousekey `Capture` 逻辑）。

---

### 4.2 平滑鼠标操作（能力 2）

#### 4.2.1 原则

- **禁止** `SetCursorPos(x, y)` 单步瞬移作为默认行为。
- 任意 `move(x, y)` 必须走**路径插值**，视觉上连贯。
- 支持 `click`、`double_click`、`drag`、`scroll`。

#### 4.2.2 路径算法（复用 mousekey humanize）

采用 **二次贝塞尔曲线 + ease-in-out 缓动**：

```
P(t) = (1-t)²·P₀ + 2(1-t)t·P₁ + t²·P₂

其中：
  P₀ = 当前鼠标位置
  P₂ = 目标位置
  P₁ = 中点 + 随机控制点偏移（可选，智能体场景可关闭随机性）
  t  经 ease 函数：ease(t) = 3t² - 2t³
```

步进参数（可配置）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `steps` | 20 | 插值步数，距离越远可自适应增加 |
| `step_delay_ms` | 5–10 | 每步间隔 |
| `curve_jitter` | false | 智能体模式关闭随机抖动 |

距离自适应步数：

```python
def adaptive_steps(distance: float) -> int:
    return clamp(int(distance / 15), min_steps=8, max_steps=60)
```

#### 4.2.3 平台实现

```python
class InputDriver(Protocol):
    def get_position(self) -> tuple[int, int]: ...
    def move_smooth(self, x: int, y: int, *, steps: int | None = None) -> None: ...
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    def drag(self, x1, y1, x2, y2) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...

class MacInputDriver(InputDriver):
    """cliclick m:x,y + w:delay 逐步执行"""

class WinInputDriver(InputDriver):
    """SendInput MOUSEEVENTF_MOVE 相对/绝对模式逐步执行"""
```

#### 4.2.4 MCP Tools

| Tool | 参数 | 行为 |
|------|------|------|
| `mouse_get_position` | — | 返回当前坐标 |
| `mouse_move` | `x`, `y`, `steps?` | 平滑移动 |
| `mouse_click` | `x`, `y`, `button?`, `clicks?` | 移动后点击 |
| `mouse_drag` | `x1`, `y1`, `x2`, `y2` | 按下→平滑拖→释放 |
| `mouse_scroll` | `dx`, `dy` | 滚轮 |

---

### 4.3 键盘操作（能力 3）

#### 4.3.1 能力范围

| 操作 | 示例 | 实现 |
|------|------|------|
| 单键 | `Enter`, `Escape`, `Tab` | 平台 key code 映射 |
| 组合键 | `Cmd+C` / `Ctrl+C` | modifier + key |
| 文本输入 | `"hello@example.com"` | 逐字符 Unicode 输入（非剪贴板） |
| 按键序列 | `Tab → Tab → Enter` | 可选复合 tool |

#### 4.3.2 键名规范

统一 **跨平台抽象键名**，内部映射：

```
cmd/super → macOS ⌘ / Windows Win
ctrl      → macOS ⌃ / Windows Ctrl
alt/option→ macOS ⌥ / Windows Alt
shift     → 两平台一致
```

MCP tool 入参使用抽象名，Driver 层做平台翻译（macOS: cliclick `kp:`；Windows: `pyautogui.hotkey`）。

#### 4.3.3 MCP Tools

| Tool | 参数 | 行为 |
|------|------|------|
| `keyboard_press` | `key` | 单键按下并释放 |
| `keyboard_hotkey` | `keys: string[]` | 组合键，如 `["cmd", "c"]` |
| `keyboard_type` | `text`, `interval_ms?` | 逐字输入，可选间隔 |

#### 4.3.4 安全护栏

- 可选「**确认模式**」：危险组合（`cmd+q`、`alt+f4`）需用户在桌面 UI 点确认。
- 速率限制：键盘输入最高 500 字符/次，防止误操作洪水。

---

### 4.4 桌面助手浮层（Companion Overlay）

#### 4.4.1 窗口特性

| 属性 | 实现 |
|------|------|
| 位置 | 默认主屏右下角，距边缘 16px；位置持久化 |
| 窗口类型 | Tauri `transparent` + `alwaysOnTop` + `decorations: false` |
| 尺寸 | 默认 360×480（可缩放）；折叠态 80×80 |
| 点击穿透 | 透明区域 `set_ignore_cursor_events(true)`；交互区 false |
| 多屏 | 跟随主屏；拖拽可跨屏（P2） |

#### 4.4.2 UI 组成

```
┌─────────────────────────┐
│      [ 📞 电话 ]         │  ← 语音通话开关
│   ┌───────────────┐     │
│   │  数字人 Live2D │     │  ← 青年女性形象，状态：idle/listening/speaking/thinking
│   └───────────────┘     │
│ ┌─────────────────────┐ │
│ │ Agent: 正在滚动页面… │ │
│ │ 用户: 阅读第三节…    │ │  ← 聊天历史 + 流式 markdown
│ └─────────────────────┘ │
│ [ 输入框…        ][发送] │
└─────────────────────────┘
```

#### 4.4.3 数字人资源

- 渲染：**Live2D Cubism** 或 **Spine 2D**（Web 运行时，Tauri WebView 内）
- 形象：原创青年女性角色（18+），商务休闲风格
- 状态机：`idle` → `thinking`（Agent 推理）→ `acting`（MCP 执行）→ `speaking`（TTS）
- Lip-sync：TTS 音频 RMS/envelope 驱动嘴型参数 `ParamMouthOpenY`

#### 4.4.4 聊天 → Agent 流水线

```
用户输入(文本/语音转写)
    │
    ▼
Companion UI ──IPC──▶ Tauri ──▶ Agent Runtime
    │                                    │
    │                                    ├─ 意图识别（本地小模型 / backend LLM）
    │                                    ├─ 规划：get_screenshot → mouse_scroll → …
    │                                    └─ 调用 MCP Tools（同进程或 stdio 转发）
    ▼
流式事件 companion.message.delta → UI 渲染
任务状态 task.progress → 数字人 thinking/acting 动画
```

**场景 E 执行策略（阅读浏览器第三节）**

1. `get_screenshot` + `get_recent_frames` 确认浏览器在前台
2. VLM/OCR 定位目录/锚点或搜索第三节标题
3. 循环 `mouse_scroll(dy=-3)` + 截帧，直到 OCR 命中「第三节」
4. 截取第三节 viewport 区域，生成摘要写入聊天框

---

### 4.5 Socket 实时桥接

#### 4.5.1 设计目标

- 弥补 stdio MCP **请求-响应**模式在高频操作下的开销
- 支持 **Server Push**（帧流、任务进度、语音识别 partial）
- 供外部 Agent（hui-agent backend、加载 Skill 的 Cursor Agent）**长连接**复用会话

#### 4.5.2 连接参数

| 项 | 默认值 |
|----|--------|
| 地址 | `127.0.0.1:18765` |
| 协议 | TCP + NDJSON（一行一 JSON） |
| 鉴权 | 首帧 `{ "type":"auth","token":"..." }` |
| 心跳 | 客户端每 15s `ping`，服务端 `pong` |

Token 来源：安装时生成 UUID 写入 `~/.hui-agent/config.json`；设置页可复制。

#### 4.5.3 消息类型

**Client → Server**

| type | 说明 |
|------|------|
| `auth` | 连接鉴权 |
| `tool.invoke` | `{ "name": "mouse_scroll", "arguments": { "dy": -5 }, "id": "..." }` |
| `chat.send` | 用户消息（外部 Agent 代发） |
| `frame.subscribe` | `{ "fps": 2 }` 订阅 push |
| `voice.start` / `voice.stop` | 通话模式 |

**Server → Client**

| type | 说明 |
|------|------|
| `tool.result` | tool 返回或错误 |
| `frame.push` | `{ "path": "...", "timestamp_ms": ... }` |
| `chat.delta` / `chat.done` | Agent 流式回复 |
| `task.progress` | `{ "step": "scroll", "message": "..." }` |
| `voice.stt.partial` / `voice.stt.final` | 语音识别 |
| `voice.tts.start` / `voice.tts.end` | TTS 生命周期 |

#### 4.5.4 与 MCP 的关系

```
                    ┌─────────────────┐
  stdio JSON-RPC    │   MCP Core      │
  ─────────────────▶│  Tool Registry  │◀────── tool.invoke (Socket)
                    │  (shared)       │
                    └────────┬────────┘
                             │
                    Capture / Input / Voice
```

Socket Bridge 与 stdio 层**共享同一 Tool Registry**，保证行为一致；并发加队列锁，键鼠操作串行化。

#### 4.5.5 Agent Skill

详见 [`skills/hui-agent-socket-bridge/SKILL.md`](skills/hui-agent-socket-bridge/SKILL.md)。Skill 指导 Agent：

1. 读取 `~/.hui-agent/config.json` 获取 port/token
2. 建立 TCP 连接并 auth
3. 任务循环：`frame.push` / `get_recent_frames` → 决策 → `tool.invoke`
4. 语音任务：监听 `voice.stt.final`，回复用 `tool.invoke(tts_speak)`

---

### 4.6 语音模块（TTS / STT）

> **TTS 详细集成见 [edge-tts-integration.md](./edge-tts-integration.md)**  
> 参考实现：`faco/office/share-web-ppt/tts-proxy.py`

#### 4.6.1 架构

```
麦克风 ──▶ STT Engine（本地 whisper）──▶ voice.stt.final ──▶ Agent Runtime
                                                              │
Agent 回复文本 ◀──────────────────────────────────────────────┘
      │
      ▼
 Edge TTS HTTP Proxy (:8896) ──▶ MP3 ──▶ 播放 + lip-sync ──▶ 数字人 + 扬声器
      ▲
 POST /tts { text, voice, rate, pitch, volume }
```

#### 4.6.2 引擎选型

| 引擎 | 平台 | 用途 | 优先级 |
|------|------|------|--------|
| **Edge TTS HTTP**（`tts-proxy.py` 同构） | macOS/Win | TTS，Neural 拟人语音 | **P1 默认** |
| **whisper.cpp** / **sherpa-onnx** | macOS/Win | STT，离线 | P1 默认 |
| **piper**（本地） | macOS/Win | TTS 离线降级 | P2 |

**Edge TTS 集成要点**

- 应用启动时 spawn **`tts_proxy` 子进程**，默认 `127.0.0.1:8896`
- 依赖 `edge-tts` Python 包，**需联网**访问 Bing Speech
- 默认音色 **`zh-CN-XiaoxiaoNeural`**（年轻自然女声，贴合数字人）
- 支持 `rate` / `pitch` / `volume` 调节语气；文本经 `_clean_text` 清洗
- **禁止**向 `Communicate` 传入完整 SSML markup

#### 4.6.3 MCP Tools

| Tool | 参数 | 行为 |
|------|------|------|
| `tts_speak` | `text`, `voice?`, `rate?`, `pitch?`, `volume?` | POST Edge TTS HTTP → 播放 MP3 |
| `tts_stop` | — | 打断当前播放 |
| `stt_listen` | `timeout_ms?`, `language?` | 本地 STT，阻塞直到一句话或超时 |
| `voice_call_start` | — | 开启通话模式（持续 listen + 自动 TTS） |
| `voice_call_stop` | — | 结束通话模式 |

#### 4.6.4 通话模式状态机

```
Idle ──(点击📞)──▶ CallActive
  CallActive: 后台 VAD 检测语音 → STT → Agent → TTS → 循环
  CallActive ──(再点📞 / tts_stop+idle)──▶ Idle
```

**场景 F（Vibe Coding）编排**

1. STT：「根据需求文档第三节…在 ~/projects/xx 开发…」
2. Agent：Edge TTS 口语确认目录与项目名（`tts_speak`，晓晓音色）
3. `keyboard_hotkey` 打开终端/IDE → `keyboard_type` 命令 → 或通过 Socket 调用 backend coding agent
4. 阶段进度经 `task.progress` + `tts_speak` 同步播报
5. 完成后 TTS 汇总 + 聊天框 markdown 报告

#### 4.6.5 权限

| 平台 | 权限 |
|------|------|
| macOS | 麦克风（`NSMicrophoneUsageDescription`） |
| Windows | 设置 → 隐私 → 麦克风 |

---

## 5. MCP 服务设计

### 5.1 传输层

| 模式 | 场景 | 配置 |
|------|------|------|
| **stdio**（默认） | Cursor / Claude Desktop 本地连接 | 桌面应用 spawn 子进程，或写入 `~/.cursor/mcp.json` |
| **Socket**（实时） | hui-agent backend / Skill Agent | `127.0.0.1:18765` NDJSON |
| **Streamable HTTP**（可选） | 远程 HTTP MCP 客户端 | 绑定 `127.0.0.1:PORT`，Bearer Token |

桌面应用启动流程：

```
1. 检查系统权限（屏幕录制、辅助功能/输入监控）
2. 启动 MCP 子进程（stdio 或 HTTP）
3. 启动 CaptureThread
4. 托盘图标显示「MCP 运行中 · 50 帧缓冲」
5. 启动 Companion 浮层 + Socket Bridge
6. 退出时 SIGTERM → 清理临时目录 → 停止子进程
```

### 5.2 Tool 清单（完整）

```
# 画面
get_recent_frames    → 物化最近 5s/50 帧到临时目录
get_screenshot       → 当前单帧快照（即时 grab，非缓冲）

# 鼠标
mouse_get_position
mouse_move
mouse_click
mouse_drag
mouse_scroll

# 键盘
keyboard_press
keyboard_hotkey
keyboard_type

# 系统
get_screen_info      → 分辨率、scale、主屏 origin
check_permissions    → 权限状态诊断

# 语音（P1）
tts_speak            → 文字转语音播报
tts_stop             → 停止播报
stt_listen           → 语音识别
voice_call_start     → 开启通话模式
voice_call_stop      → 关闭通话模式
```

### 5.3 Cursor 配置示例

```json
{
  "mcpServers": {
    "hui-agent-desktop": {
      "command": "/Applications/HuiAgent.app/Contents/MacOS/hui-mcp-server",
      "args": ["--stdio"],
      "env": {
        "HUI_AGENT_FRAME_DIR": "/tmp/hui-agent-frames"
      }
    }
  }
}
```

Windows 等价路径：`C:\\Program Files\\HuiAgent\\hui-mcp-server.exe`

---

## 6. 桌面应用（Tauri Shell）

### 6.1 功能模块

| 模块 | 职责 |
|------|------|
| 系统托盘 | 启动/停止 MCP、显示/隐藏助手、退出 |
| **Companion Overlay** | 聊天框、数字人、电话按钮、任务状态 |
| **Agent Runtime** | 意图理解、Tool 编排、流式回复 |
| 权限向导 | 屏幕录制、辅助功能、麦克风 |
| 设置页 | MCP/Socket/语音/浮层配置 |
| 日志查看 | MCP stderr + Socket 连接日志 |
| 自动更新 | Tauri updater（可选二期） |

### 6.2 目录结构（建议）

```
repo/client/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs
│   │   ├── companion/       # 浮层窗口管理
│   │   ├── permissions/
│   │   └── process.rs
│   └── tauri.conf.json
├── ui/
│   ├── settings/            # 设置页
│   └── companion/           # 聊天+Live2D
│       ├── ChatPanel.tsx
│       └── AvatarLive2D.tsx
├── agent-runtime/           # 任务编排（TS 或 Python）
│   ├── orchestrator.ts
│   └── prompts/
├── mcp-server/
│   ├── server.py
│   ├── socket_bridge.py
│   ├── capture/
│   ├── input/
│   ├── voice/
│   │   ├── tts_proxy.py      # Edge TTS HTTP（同 tts-proxy.py）
│   │   ├── tts_client.py     # POST /tts 客户端
│   │   └── stt.py            # whisper 本地 STT
│   └── tools/
└── scripts/
```

### 6.3 打包与分发

| 平台 | 产物 | 备注 |
|------|------|------|
| macOS | `HuiAgent.dmg` / `.app` | 需 Apple 公证；内嵌 Python venv 或 PyInstaller 单文件 |
| Windows | `HuiAgent-setup.exe` (NSIS) | 内嵌 Python；安装时注册 MCP 路径到用户文档 |

MCP Server 打包策略：

- **PyInstaller `--onefile`** 打入 Tauri resources，Tauri 启动时解压到 cache 并 exec；
- 或 **uv/venv 随包携带**（体积略大，调试方便）。

---

## 7. 权限与合规

### 7.1 macOS

| 权限 | 用途 | 检测方式 |
|------|------|----------|
| 屏幕录制 | mss 截屏 | `CGPreflightScreenCaptureAccess` |
| 辅助功能 | cliclick 键鼠 | `AXIsProcessTrusted` |
| 输入监控 | 键盘监听（若需） | `IOHIDCheckAccess` |
| **麦克风** | STT / 通话模式 | `AVCaptureDevice` 授权 |

首次启动弹出引导页，深链接到「系统设置 → 隐私与安全性」。

### 7.2 Windows

| 权限 | 用途 |
|------|------|
| 无特殊权限（标准用户） | SendInput / GDI 截屏 |
| UAC | 不提升；若目标为 elevated 窗口需另议（本期不支持） |

### 7.3 安全原则

- MCP HTTP 模式仅监听 `127.0.0.1`，Bearer token 必填。
- 临时帧目录权限 `0700`，不含用户敏感信息以外的额外数据。
- 所有 tool 调用写 audit log（本地轮转，不上云）。

---

## 8. 性能与资源预算

| 指标 | 目标 |
|------|------|
| 采集 CPU | < 5%（1080p, 10fps, mss） |
| 采集内存 | 环形缓冲 ~50 × 200KB PNG ≈ 10MB 磁盘；内存中仅当前帧 |
| MCP 冷启动 | < 2s |
| Socket 握手 | < 200ms |
| TTS 首包（Edge，短句） | < 1.5s |
| STT 句末延迟 | < 800ms |
| 鼠标移动 500px | 200–800ms（可配置） |
| 临时目录 IO | 每次 tool 调用复制 50 帧 ≈ 10MB，SSD < 100ms |

优化手段：

- 环形缓冲**原地覆盖** PNG，避免频繁 mkdir。
- `get_recent_frames` 默认 hardlink（同盘）而非 copy。
- 可选 JPEG quality=85 降低体积（配置项）。

---

## 9. 测试策略

| 层级 | 内容 |
|------|------|
| 单元测试 | `smooth_path` 插值点数、ease 单调性、键名映射 |
| 集成测试 | mock driver 下 MCP tool 调用链 |
| E2E | 启动 MCP → `get_recent_frames` 返回 50 帧 → `mouse_move` 验证坐标变化 |
| 人工 | macOS / Windows 各一台，权限向导、Retina 坐标、多语言键盘 |

---

## 10. 实施计划

| 阶段 | 交付物 | 工期（估） |
|------|--------|-----------|
| **P0** | Python MCP Server：帧缓冲 + 3 个 mouse tool + 2 个 keyboard tool，stdio 模式 | 1 周 |
| **P1** | Tauri 壳：托盘、spawn MCP、权限检测、Cursor 配置导出 | 1 周 |
| **P2** | Windows InputDriver + 跨平台打包 | 1  week |
| **P3** | Companion 浮层 + Agent Runtime + 场景 E | 1.5 周 |
| **P4** | Socket Bridge + Skill + Edge TTS/STT + 场景 F | 2 周 |
| **P5** | HTTP 传输 + backend 联调 + audit log | 1 周 |
| **P6** | 安装包签名、文档、E2E 测试 | 0.5 周 |

---

## 11. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| macOS 权限用户拒绝 | 截屏/键鼠不可用 | 托盘红色状态 + 引导页；`check_permissions` tool |
| Retina 坐标偏移 | 点击错位 | manifest 带 scale；统一逻辑点坐标；E2E 校准测试 |
| MCP stdout 污染 | 协议崩溃 | 强制 logging 走 stderr；CI lint 检测 print |
| Windows 管理员窗口 | SendInput 失效 | 文档说明限制；返回明确错误码 |
| 帧目录磁盘占满 | 服务异常 | TTL 清理 + 最大目录数限制 |
| Live2D 性能 | 低配机卡顿 | 降级静态 PNG 形象 |
| Edge TTS 网络不可用 | 无法播报 | 明确错误提示；P2 piper 降级 |
| STT 误识别 | 错误任务 | 关键操作 TTS 确认；Push-to-talk 可选 |
| Socket 未鉴权 | 本地恶意调用 | 127.0.0.1 + Token  mandatory |

---

## 12. 参考

- [MCP 规范 - stdio 传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- 同仓库 `mousekey/`：`src/capture.py`（mss 截屏）、`src/actuator/humanize.py`（贝塞尔平滑移动）
- 开源参考：[ControlMCP](https://github.com/nix18/ControlMCP)、[mcp-desktop-pro](https://github.com/lksrz/mcp-desktop-pro)

---

## 附录 A：MCP Tool Schema 示例

```json
{
  "name": "get_recent_frames",
  "description": "获取最近 5 秒桌面逐帧截图（10fps，共 50 帧），写入临时目录并返回路径与 manifest",
  "inputSchema": {
    "type": "object",
    "properties": {
      "monitor": { "type": "integer", "default": 0, "description": "显示器索引，0=主屏" },
      "format": { "type": "string", "enum": ["png", "jpeg"], "default": "png" }
    }
  }
}
```

```json
{
  "name": "mouse_move",
  "description": "平滑移动鼠标到目标坐标（禁止瞬移）",
  "inputSchema": {
    "type": "object",
    "required": ["x", "y"],
    "properties": {
      "x": { "type": "integer" },
      "y": { "type": "integer" },
      "steps": { "type": "integer", "description": "插值步数，默认按距离自适应" }
    }
  }
}
```

---

## 附录 B：与 mousekey 的复用关系

| mousekey 模块 | hui-agent client 复用方式 |
|---------------|--------------------------|
| `src/capture.py` | 提取为 `mcp-server/capture/grabber.py`，增加 RingBuffer |
| `src/actuator/humanize.py` | 提取为 `input/smooth_path.py` + `input/mac.py` |
| `gui/panel.py` | **不复用**；Tauri UI 替代 |
| HID 后端 | 本期不做；接口预留 `InputDriver` 扩展点 |

---

## 附录 C：Socket 消息示例

**鉴权**

```json
{"type":"auth","token":"8f3c2a1b-..."}
{"type":"auth.ok","session_id":"s1"}
```

**Tool 调用**

```json
{"type":"tool.invoke","id":"t1","name":"mouse_scroll","arguments":{"dy":-5}}
{"type":"tool.result","id":"t1","ok":true,"result":{"scrolled":true}}
```

**任务进度**

```json
{"type":"task.progress","task_id":"read-doc-3","step":"scroll","message":"正在滚动至第三节…"}
```

**语音**

```json
{"type":"voice.stt.final","text":"帮我在 projects 目录开发 xx 项目","confidence":0.92}
{"type":"tool.invoke","id":"t2","name":"tts_speak","arguments":{"text":"好的，正在为您创建项目…"}}
```

---

## 附录 D：修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-07-26 | 初稿：MCP 截屏/键鼠 |
| v1.1 | 2026-07-26 | 新增 Companion、Socket、语音模块 |
| v1.2 | 2026-07-26 | TTS 优先 Edge TTS HTTP（tts-proxy 同构） |
