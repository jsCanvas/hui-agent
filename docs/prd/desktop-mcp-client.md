# 桌面端 MCP 客户端 PRD

> 文档版本：v1.2  
> 日期：2026-07-26  
> 所属项目：hui-agent / repo/client  
> 关联文档：[技术方案](../solution/desktop-mcp-client.md) · [Edge TTS 集成](../solution/edge-tts-integration.md) · [Socket Skill](../solution/skills/hui-agent-socket-bridge/SKILL.md) · [Companion 使用说明](./companion-usage.md)  
> 状态：需求评审

---

## 1. 文档说明

### 1.1 目的

定义 hui-agent 桌面端客户端的产品需求，明确「为谁、解决什么问题、做到什么程度」，作为设计、开发、测试与验收的统一依据。

### 1.2 范围

| 在范围内 | 不在范围内（本期） |
|----------|-------------------|
| macOS、Windows 桌面应用 | Linux 桌面 |
| 启动并托管 MCP 服务 | 云端远程桌面（VNC/RTC） |
| 桌面画面缓冲、鼠标、键盘能力 | 硬件 HID 后端 |
| **桌面右下角浮层：聊天框 + 数字人助手** | 多显示器独立控制 |
| **Socket 实时桥接 + Agent Skill** | 应用商店自动更新（二期） |
| **语音通话：TTS 播报 + 用户语音识别** | 离线 TTS 引擎（Edge TTS 优先，离线作降级） |
| 系统托盘、权限引导、基础设置 | 3D 超写实数字人（首期 2D/Live2D） |
| Cursor / Claude 本地 MCP 接入 | |

---

## 2. 产品背景

### 2.1 问题陈述

hui-agent 智能体需要在本机完成「观察屏幕 → 理解界面 → 操作键鼠」的闭环。当前 backend / web 运行在容器内，**无法直接访问用户桌面**。缺少标准化、可对接 AI 工具链（Cursor、Claude Desktop、hui-agent backend）的本地控制入口。

### 2.2 产品定位

**HuiAgent Desktop** 是 hui-agent 平台的本地代理：用户安装并打开后，在本机启动 MCP 服务，将桌面画面与键鼠控制能力以标准协议暴露给智能体；同时在桌面右下角呈现**可对话的数字人助手**，支持文字任务派发与语音通话，实现「看得见、说得清、做得动」的桌面 AI 伴侣。

### 2.3 产品价值

| 对象 | 价值 |
|------|------|
| 终端用户 | 一键安装，授权后即可让 AI 辅助完成重复性桌面操作 |
| 智能体 / 开发者 | 统一 MCP Tool 接口，无需为每个 Host 单独集成 |
| hui-agent 平台 | client 与 backend / web 解耦，桌面能力本地化、合规可控 |

---

## 3. 用户与场景

### 3.1 目标用户

| 角色 | 描述 | 核心诉求 |
|------|------|----------|
| **个人效率用户** | 使用 Cursor / Claude 的开发者或知识工作者 | 快速接入、权限清晰、操作可预期 |
| **自动化测试人员** | 需要 AI 驱动 UI 操作验证 | 稳定截帧、坐标准确、可回放上下文 |
| **hui-agent 管理员** | 部署 backend + web，管理多终端 | 可观测 client 在线状态（二期 HTTP 模式） |

### 3.2 典型场景

**场景 A：AI 理解近期操作**

> 用户在 Finder 中连续点击多个文件夹，随后对 Cursor 说：「帮我总结一下刚才浏览了哪些目录。」  
> 智能体调用 `get_recent_frames`，读取最近 5 秒 50 帧截图，结合 manifest 时间线理解操作序列。

**场景 B：AI 填写表单**

> 用户让 AI 在本地应用中填写注册表单。  
> 智能体先 `get_screenshot` 定位字段，再 `mouse_click` 聚焦、`keyboard_type` 输入文本、`keyboard_hotkey` 提交。

**场景 C：首次安装授权**

> 用户首次打开 HuiAgent Desktop，应用检测到 macOS 未授予「屏幕录制」和「辅助功能」，弹出引导页，逐步完成授权后 MCP 自动启动，托盘显示绿色「运行中」。

**场景 D：开发者在 Cursor 中配置 MCP**

> 用户在设置页点击「导出 Cursor 配置」，将 MCP Server 路径写入 `~/.cursor/mcp.json`，重启 Cursor 后即可使用全部 desktop tools。

**场景 E：聊天框派发桌面浏览任务**

> 用户在浏览器打开需求文档，在右下角聊天框输入：「阅读桌面浏览器网页上的 XX 需求文档的第三节。」  
> 智能体通过 MCP 获取当前截图与近期帧 → 识别浏览器窗口 → 平滑滚动页面 → 定位第三节 → 在聊天框流式回复摘要。

**场景 F：语音通话派发开发任务（Vibe Coding）**

> 用户点击数字人上方「电话」按钮进入通话模式，说：「帮我根据需求文档第三节内容和接口文档规范，在 `~/projects/xx` 目录下开发 XX 项目。」  
> 智能体语音确认任务要点 → TTS 播报进度 → 自动切换/操作 IDE 与终端 → 在指定目录执行 vibe coding，过程中通过语音汇报里程碑。

**场景 G：外部智能体 Socket 实时联调**

> hui-agent backend 或 Cursor Agent 加载 Socket Skill，连接本机 `127.0.0.1:18765`，订阅 `frame.push` 与 `task.progress` 事件，实时下发 `mouse_scroll` / `keyboard_type` 而无需逐次冷启动 MCP stdio。

---

## 4. 产品目标

### 4.1 业务目标

1. 用户从安装到 MCP 可用 **≤ 5 分钟**（含权限授权）。
2. 支持 **macOS 12+**、**Windows 10+** 双平台一致体验。
3. 与 Cursor / Claude Desktop 通过 **stdio MCP** 即插即用。

### 4.2 成功指标（上线后 30 天）

| 指标 | 目标 |
|------|------|
| 安装后 MCP 成功启动率 | ≥ 90% |
| 权限引导完成率 | ≥ 80% |
| `get_recent_frames` 调用成功率 | ≥ 99% |
| 鼠标点击坐标偏差（1080p 逻辑坐标） | ≤ 2 px |
| 聊天任务从发送到首条 Agent 回复 | ≤ 3s（本地 backend） |
| 语音识别句末延迟（P1） | ≤ 800ms |
| TTS 首包延迟（P1，Edge TTS） | ≤ 1.5s（含 HTTP 合成；短句目标 ≤ 800ms） |
| 应用崩溃率（Sessions） | ≤ 0.5% |

---

## 5. 功能需求

### 5.1 功能总览

```
P0 必须交付                    P1 应当交付                 P2 可选 / 二期
─────────────────────────────────────────────────────────────────────────
桌面应用壳 + 系统托盘           HTTP MCP 模式               开机自启动
MCP 服务自动启动               Socket 实时桥接              自动更新
权限检测与引导                 Agent Socket Skill           多显示器选择
get_recent_frames (5s/10fps)   语音通话（TTS + STT）        硬件 HID 扩展
平滑鼠标全套 tools             数字人口型同步               Live2D 换肤
键盘全套 tools                 hui-agent backend 联调
get_screenshot / get_screen_info  危险操作确认模式
check_permissions              audit 本地日志
Cursor MCP 配置导出
桌面浮层：聊天框 + 数字人助手
聊天任务派发 → Agent 执行
macOS + Windows 安装包
```

### 5.2 FR-01 桌面应用与生命周期

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-01-01 | 提供 macOS `.app`/`.dmg` 与 Windows 安装包，用户双击即可安装 | P0 |
| FR-01-02 | 应用启动后**默认自动启动 MCP 服务**，无需手动命令行 | P0 |
| FR-01-03 | 系统托盘常驻：显示 MCP 运行状态（运行中 / 已停止 / 权限缺失） | P0 |
| FR-01-04 | 托盘菜单：打开设置、启动/停止 MCP、导出 Cursor 配置、退出 | P0 |
| FR-01-05 | 退出应用时优雅停止 MCP 子进程并清理临时帧目录 | P0 |
| FR-01-06 | 支持开机自启动（默认关闭，设置中可开启） | P2 |

**验收标准**

- [ ] 安装后首次打开，30 秒内托盘出现且 MCP 状态可辨识
- [ ] 点击退出后，无残留 MCP 子进程（`ps` / 任务管理器验证）
- [ ] 停止 MCP 后，Cursor 侧连接断开并收到明确错误

---

### 5.3 FR-02 权限与引导

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-02-01 | macOS：检测「屏幕录制」「辅助功能」权限状态 | P0 |
| FR-02-02 | macOS：权限缺失时展示引导页，提供跳转系统设置的说明 | P0 |
| FR-02-03 | Windows：无需额外权限弹窗；若操作失败返回可读错误 | P0 |
| FR-02-04 | MCP Tool `check_permissions` 返回各权限项 pass/fail 及修复建议 | P0 |
| FR-02-05 | 权限未就绪时，截屏/键鼠 tools 返回结构化错误，不静默失败 | P0 |

**验收标准**

- [ ] macOS 未授权屏幕录制时，`get_recent_frames` 返回 `PERMISSION_DENIED` 及引导文案
- [ ] 授权完成后无需重启应用即可恢复能力（或明确提示需重启一次）

---

### 5.4 FR-03 桌面画面采集

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-03-01 | MCP 服务运行期间，后台以 **10 fps** 持续采集**主显示器**画面 | P0 |
| FR-03-02 | 维护 **5 秒 / 50 帧**环形缓冲，内存与磁盘占用可控 | P0 |
| FR-03-03 | Tool `get_recent_frames`：将缓冲物化到临时目录，返回目录路径 + `manifest.json` | P0 |
| FR-03-04 | `manifest.json` 含：时间戳、帧列表、分辨率、scale_factor、fps | P0 |
| FR-03-05 | Tool `get_screenshot`：返回当前单帧（即时抓取，不走缓冲） | P0 |
| FR-03-06 | 临时目录 TTL **10 分钟**自动清理；权限 `0700` | P0 |
| FR-03-07 | 默认 PNG；高级设置可选 JPEG（quality 85） | P1 |
| FR-03-08 | 多显示器：首期仅主屏；设置页预留显示器选择 | P2 |

**manifest 最低字段要求**

```json
{
  "version": 1,
  "captured_at_ms": 0,
  "duration_sec": 5.0,
  "fps": 10,
  "frame_count": 50,
  "monitor": { "id": 0, "width": 0, "height": 0, "scale_factor": 1.0 },
  "frames": [{ "file": "...", "index": 0, "timestamp_ms": 0 }]
}
```

**验收标准**

- [ ] 缓冲运行 10 分钟后，环形缓冲文件数仍为 50，不无限增长
- [ ] `get_recent_frames` 返回帧数 = 50（服务启动满 5 秒后；不足 5 秒则返回已有帧并注明实际 duration）
- [ ] 连续调用 100 次，无磁盘占满或泄漏
- [ ] macOS Retina 下 manifest 中 `scale_factor` ≥ 1，且与 `get_screen_info` 一致

---

### 5.5 FR-04 鼠标操作

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-04-01 | 所有移动类操作必须**平滑路径**到达目标，禁止默认瞬移 | P0 |
| FR-04-02 | Tool `mouse_get_position`：返回当前光标逻辑坐标 | P0 |
| FR-04-03 | Tool `mouse_move`：平滑移动至 (x, y)，支持可选 `steps` | P0 |
| FR-04-04 | Tool `mouse_click`：移动后点击，支持 left/right/middle、单击/双击 | P0 |
| FR-04-05 | Tool `mouse_drag`：按下 → 平滑拖动 → 释放 | P0 |
| FR-04-06 | Tool `mouse_scroll`：水平/垂直滚轮 | P0 |
| FR-04-07 | 移动耗时随距离自适应（约 200–800ms / 500px），可在高级设置调节 | P1 |

**验收标准**

- [ ] 屏幕录制对比：`mouse_move` 轨迹为连续曲线，无单帧跳跃 > 50px（1080p）
- [ ] `mouse_click` 后，目标应用收到正确点击事件
- [ ] 跨平台坐标系：与 `get_screen_info` 返回的逻辑分辨率一致

---

### 5.6 FR-05 键盘操作

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-05-01 | Tool `keyboard_press`：单键（Enter、Tab、Escape 等） | P0 |
| FR-05-02 | Tool `keyboard_hotkey`：组合键，使用跨平台抽象名（cmd/ctrl/alt/shift） | P0 |
| FR-05-03 | Tool `keyboard_type`：Unicode 文本输入，单次 ≤ 500 字符 | P0 |
| FR-05-04 | macOS `cmd` 映射 ⌘，Windows `cmd` 映射 Win 键 | P0 |
| FR-05-05 | 危险组合（cmd+q、alt+f4）默认拦截或需用户确认（可配置） | P1 |

**验收标准**

- [ ] 在记事本 / TextEdit 中 `keyboard_type` 输入中英文与符号正确
- [ ] `keyboard_hotkey(["cmd", "c"])` / `keyboard_hotkey(["ctrl", "c"])` 在对应平台触发复制
- [ ] 超过 500 字符请求返回 `VALIDATION_ERROR`

---

### 5.7 FR-06 MCP 服务与对接

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-06-01 | 实现 MCP 标准 Tool 清单（见 §5.8） | P0 |
| FR-06-02 | 默认 **stdio** 传输，兼容 Cursor / Claude Desktop | P0 |
| FR-06-03 | 设置页「导出 Cursor 配置」生成可复制 JSON | P0 |
| FR-06-04 | 日志仅写 stderr，**禁止污染 stdout** | P0 |
| FR-06-05 | 可选 Streamable HTTP，绑定 127.0.0.1，Bearer Token 鉴权 | P1 |
| FR-06-06 | Tool `get_screen_info`：分辨率、scale、主屏 origin | P0 |

**验收标准**

- [ ] Cursor 加载配置后，可列出全部 P0 tools 并成功调用
- [ ] MCP 协议握手与 tool call 符合 MCP 2025-11-25 规范
- [ ] HTTP 模式无 Token 请求返回 401

---

### 5.8 MCP Tool 清单（产品视角）

| Tool | 用户可感知能力 | 优先级 |
|------|----------------|--------|
| `get_recent_frames` | 获取最近 5 秒操作画面 | P0 |
| `get_screenshot` | 获取当前屏幕快照 | P0 |
| `get_screen_info` | 查询屏幕参数 | P0 |
| `check_permissions` | 诊断权限问题 | P0 |
| `mouse_get_position` | 读取鼠标位置 | P0 |
| `mouse_move` | 平滑移动 | P0 |
| `mouse_click` | 点击 | P0 |
| `mouse_drag` | 拖拽 | P0 |
| `mouse_scroll` | 滚轮 | P0 |
| `keyboard_press` | 单键 | P0 |
| `keyboard_hotkey` | 组合键 | P0 |
| `keyboard_type` | 输入文本 | P0 |
| `tts_speak` | 语音播报（通话模式） | P1 |
| `stt_listen` | 语音识别（通话模式） | P1 |

---

### 5.9 FR-07 设置与可观测性

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-07-01 | 设置页：MCP 启停、Cursor 配置导出 | P0 |
| FR-07-02 | 设置页：查看 MCP 最近日志（stderr 尾部） | P1 |
| FR-07-03 | 设置页：HTTP 端口与 Token（P1 功能） | P1 |
| FR-07-04 | 本地 audit log：记录 tool 名称、时间、参数摘要（不含帧内容） | P1 |
| FR-07-05 | 高级设置：帧率、缓冲时长、鼠标速度档位 | P2 |
| FR-07-06 | 设置页：浮层显示/隐藏、透明度、贴边位置 | P1 |
| FR-07-07 | 设置页：Socket 端口、Edge TTS 音色/语速/音调、STT 引擎 | P1 |

---

### 5.10 FR-08 桌面浮层与数字人助手

应用启动后，在**主显示器右下角**展示常驻浮层，包含聊天框与数字人形象，不遮挡系统关键 UI（可拖拽、可最小化）。

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-08-01 | 浮层默认停靠右下角，支持拖拽 reposition、贴边吸附 | P0 |
| FR-08-02 | 浮层窗口：**透明背景、置顶、点击穿透可选**（仅非交互区域穿透） | P0 |
| FR-08-03 | 展示**青年女性数字人助手**形象（2D/Live2D），风格专业亲和，年龄设定 18+ | P0 |
| FR-08-04 | 数字人上方展示**「电话」按钮**，点击进入/退出语音通话模式 | P1 |
| FR-08-05 | 聊天框支持：文字输入、Enter 发送、Shift+Enter 换行、历史记录滚动 | P0 |
| FR-08-06 | 聊天框展示 Agent 流式回复、任务状态（思考中 / 执行中 / 完成） | P0 |
| FR-08-07 | 用户消息一键派发至本地 Agent Runtime，触发 MCP 工具链 | P0 |
| FR-08-08 | 通话模式下数字人展示「正在听 / 正在说」状态动画 | P1 |
| FR-08-09 | TTS 播报时数字人**口型/表情**与音频同步（基础 lip-sync） | P1 |
| FR-08-10 | 浮层可折叠为仅头像气泡，单击展开 | P1 |

**典型任务验收（场景 E）**

用户输入：「阅读桌面浏览器网页上的 XX 需求文档的第三节。」

- [ ] Agent 在 30 秒内完成：定位浏览器 → 滚动至第三节 → 聊天框输出第三节摘要
- [ ] 执行过程可在聊天框看到步骤说明（如「正在滚动页面…」）
- [ ] 鼠标滚动为平滑操作，非瞬移

---

### 5.11 FR-09 Socket 实时桥接与 Agent Skill

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-09-01 | MCP 服务启动时同步启动 **Socket Bridge**（默认 `127.0.0.1:18765`） | P1 |
| FR-09-02 | Socket 协议支持：连接鉴权、心跳、JSON 消息帧、流式事件 | P1 |
| FR-09-03 | 支持 `tool.invoke` / `tool.result` 实时调用全部 MCP Tools | P1 |
| FR-09-04 | 支持 `frame.push` 事件：按配置推送截图或帧 manifest（可选 1–10 fps） | P1 |
| FR-09-05 | 支持 `chat.message` / `task.progress` / `task.complete` 任务生命周期事件 | P1 |
| FR-09-06 | 提供 **Agent Skill** 文档（`docs/solution/skills/hui-agent-socket-bridge/SKILL.md`），指导智能体连接 Socket | P1 |
| FR-09-07 | Skill 含：启动/连接示例、消息 schema、错误码、重连策略 | P1 |
| FR-09-08 | 仅监听 `127.0.0.1`；连接需 Token（与 HTTP MCP 共用或独立） | P1 |
| FR-09-09 | 设置页展示 Socket 地址与 Skill 安装说明 | P1 |

**验收标准**

- [ ] 外部进程按 Skill 连接后 1s 内完成握手
- [ ] 连续 100 次 `tool.invoke` 无连接泄漏
- [ ] 断线后客户端 5s 内自动重连（Agent 侧可配置）

---

### 5.12 FR-10 语音通话（TTS / STT）

#### 5.12.1 TTS 策略（拟人化优先）

**TTS 默认且优先使用 Edge TTS HTTP 服务**，参考实现见 `office/share-web-ppt/tts-proxy.py`。目标是在首期即达到**拟人化、真实语气**的播报效果，而非机械离线音。

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-10-T01 | 应用启动时随 MCP **自动拉起 Edge TTS Proxy**（内嵌同逻辑或 spawn 子进程） | P1 |
| FR-10-T02 | 默认监听 `127.0.0.1:8896`（`TTS_PROXY_PORT` 可配置） | P1 |
| FR-10-T03 | 提供 HTTP API：`POST /tts` JSON → `audio/mpeg`；`GET /health` 健康检查 | P1 |
| FR-10-T04 | 默认音色 **`zh-CN-XiaoxiaoNeural`**（晓晓，年轻自然女声，贴合数字人形象） | P1 |
| FR-10-T05 | 支持 `rate` / `pitch` / `volume` 参数（如 `rate: "+5%"`）微调语气 | P1 |
| FR-10-T06 | 合成前**文本清洗**：去除 URL、避免朗读 `http://` 等技术字符串（同 tts-proxy `_clean_text`） | P1 |
| FR-10-T07 | 传入内容为**纯文本**，禁止完整 SSML markup（edge-tts 会将标签念出） | P1 |
| FR-10-T08 | Edge TTS 不可用时（无网络/服务宕机）降级本地引擎（piper），设置页可手动切换 | P2 |
| FR-10-T09 | 设置页：音色选择（Edge Neural 列表）、语速/音调预设（「自然 / 活泼 / 沉稳」） | P1 |

**POST /tts 请求体（产品约定）**

```json
{
  "text": "好的，我正在为您滚动页面，请稍等。",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": "+5%",
  "pitch": "+2Hz",
  "volume": "+0%"
}
```

**拟人化播报规范**

- 进度播报使用**短句 + 自然停顿**，避免一次合成超过 120 字
- 确认类话术采用口语化模板（「好的，我先帮您看一下…」「第三节找到了，内容摘要如下…」）
- 数字、路径在 TTS 前转为可读中文（如 `~/projects/demo` → 「项目 demo 目录」）

#### 5.12.2 STT 与通话模式

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-10-01 | 点击「电话」进入通话模式：开启麦克风采集与 TTS 播放 | P1 |
| FR-10-02 | MCP Tool `tts_speak`：调用 Edge TTS HTTP 合成并播放，返回 `duration_ms` / `voice` | P1 |
| FR-10-03 | MCP Tool `stt_listen`：启动一次聆听，返回识别文本（可设 timeout_ms） | P1 |
| FR-10-04 | Socket 事件 `voice.tts.start` / `voice.tts.end`、`voice.stt.partial` / `voice.stt.final` | P1 |
| FR-10-05 | 用户语音经 STT 转写后**等同聊天框消息**进入 Agent 流水线 | P1 |
| FR-10-06 | 支持**打断**：用户说话时停止当前 TTS 播放（`tts_stop`） | P1 |
| FR-10-07 | macOS 需麦克风权限；Windows 需麦克风隐私授权 | P1 |
| FR-10-08 | **STT 默认本地**（whisper.cpp / sherpa-onnx）；TTS **默认 Edge HTTP** | P1 |
| FR-10-09 | 通话模式支持长任务：如「在 XX 目录 vibe coding 开发 XX 项目」 | P1 |
| FR-10-10 | TTS 播放时驱动数字人 `speaking` 状态与基础 lip-sync | P1 |

**典型任务验收（场景 F）**

用户语音：「帮我根据需求文档第三节和接口规范，在 `~/projects/demo` 下开发 XX 项目。」

- [ ] Agent 以 **Edge TTS 自然女声**复述关键信息并请求确认（非机械音）
- [ ] 确认后自动操作 IDE/终端，TTS 分句播报阶段进度
- [ ] 任务结束 TTS 口语化汇总交付物路径

**语音与 Socket 关系**

- 通话模式下，Agent 优先通过 **Socket** 下发 `tts_speak` / 接收 `voice.stt.final`；`tts_speak` 内部走 Edge TTS HTTP，stdio MCP 仍可用于 Cursor 并行接入。

---

## 6. 非功能需求

### 6.1 性能

| 指标 | 要求 |
|------|------|
| 应用冷启动到 MCP Ready | ≤ 3s（P0 目标 2s） |
| 后台采集 CPU 占用 | ≤ 5%（1080p，10fps，空闲桌面） |
| `get_recent_frames` 响应 | ≤ 500ms（含物化 50 帧，SSD） |
| 聊天首 token 延迟 | ≤ 2s（本地 Agent） |
| Socket tool 调用 RTT | ≤ 100ms（本机） |
| 安装包体积 | macOS ≤ 60MB，Windows ≤ 70MB（含语音资源可选分包） |

### 6.2 可靠性

- MCP 子进程异常退出时，托盘状态变红，支持一键重启
- 连续运行 24 小时无内存泄漏（内存增长 < 10%）
- 崩溃后重启可恢复 MCP 服务

### 6.3 安全与隐私

| 要求 | 说明 |
|------|------|
| 本地优先 | 帧截图与 audit log 默认不上传云端 |
| 网络暴露 | HTTP 仅 127.0.0.1；必须 Token |
| 目录权限 | 临时帧目录 0700 |
| 透明告知 | 首次启动说明将采集屏幕并控制键鼠，需用户主动授权 |
| 紧急停止 | 托盘「停止 MCP」立即停止一切 tool 执行 |
| 语音数据 | STT 音频默认不落盘；可选本地调试录音（默认关） |
| 数字人形象 | 使用原创/授权素材；符合平台内容规范 |

### 6.4 兼容性

| 平台 | 最低版本 |
|------|----------|
| macOS | 12 Monterey |
| Windows | 10 1903+ |

### 6.5 可用性

- 权限引导文案中英双语（首期中文为主，关键术语保留英文）
- 错误信息包含：**发生了什么 / 为什么 / 用户如何修复**
- 设置页关键操作有确认（停止 MCP、退出应用）

---

## 7. 用户体验要求

### 7.1 信息架构

```
系统托盘
├── 状态：MCP 运行中 / 已停止 / 需要权限
├── 显示/隐藏桌面助手
├── 打开设置
├── 启动 MCP / 停止 MCP
├── 导出 Cursor 配置
└── 退出

桌面浮层（右下角）
├── 数字人形象（青年女性助手）
│   └── 📞 电话按钮 → 语音通话模式
├── 聊天框
│   ├── 消息历史（用户 / Agent）
│   ├── 任务状态条
│   └── 输入框 + 发送
└── 折叠/拖拽手柄

设置页
├── 概览（状态、版本、一键复制 MCP 路径）
├── 助手（浮层开关、透明度、位置重置）
├── 权限（检测结果 + 引导链接）
├── 连接（Cursor 配置、Socket 端口、HTTP 设置）
├── 语音（STT/TTS 引擎、麦克风测试）
├── 日志
└── 高级（帧率、缓冲、鼠标速度）
```

### 7.2 状态定义

| 状态 | 托盘表现 | 用户动作 |
|------|----------|----------|
| 运行中 | 绿色图标 | 可正常使用 MCP |
| 已停止 | 灰色图标 | 点击「启动 MCP」 |
| 权限缺失 | 黄色/红色图标 | 打开权限引导 |
| 异常 | 红色图标 + 提示 | 查看日志 / 重启 MCP |

### 7.3 首次启动流程

```
安装 → 打开应用 → 欢迎页（能力说明 + 隐私提示）
    → 权限检测 → [macOS] 引导授权
    → 自动启动 MCP → 托盘「运行中」
    → 右下角浮层出现（数字人 + 聊天框）
    → 可选：导出 Cursor 配置 → 完成
```

---

## 8. 版本规划

### 8.1 MVP（v0.1 — P0）

**目标**：开发者可在 Cursor 中通过 MCP 看屏幕、控键鼠。

交付：

- Tauri 托盘应用 + MCP 自动启动
- 全部 P0 MCP Tools
- macOS 权限引导 + Cursor 配置导出
- macOS 安装包

### 8.2 v0.2 — P0 完整（键鼠 MCP）

**目标**：Windows 用户同等 MCP 能力。

交付：

- Windows InputDriver
- Windows 安装包
- 双平台 MCP E2E 测试通过

### 8.3 v0.3 — 交互增强

**目标**：桌面助手可对话、可派发任务。

交付：

- 桌面浮层（聊天框 + 数字人）
- 内置 Agent Runtime 对接 MCP
- 聊天任务派发（浏览器阅读等桌面操作场景）
- E2E：场景 E 验收通过

### 8.4 v0.4 — 实时与语音（P1）

**目标**：Socket 实时联调 + 语音通话。

交付：

- Socket Bridge + Agent Skill
- TTS / STT Tools 与电话模式
- 数字人口型同步
- 场景 F（vibe coding 语音任务）验收

### 8.5 v0.5 — 运维对接

**目标**：可运维、可对接 hui-agent backend。

交付：

- HTTP MCP + Token
- audit log
- 危险操作确认模式
- backend 联调文档

### 8.6 后续版本（P2+）

- 开机自启动、自动更新
- 多显示器
- hui-agent web 展示 client 在线状态
- 硬件 HID 后端（参考 mousekey）

---

## 9. 依赖与约束

### 9.1 系统依赖

| 平台 | 依赖 |
|------|------|
| macOS | 屏幕录制 + 辅助功能 + 麦克风；cliclick 或内嵌；**TTS 需可访问 Edge TTS 服务（网络）** |
| 网络 | Edge TTS 合成需联网；离线时降级本地 TTS（P2） |
| Windows | 标准用户权限；不支持 UAC 提升窗口内操作 |

### 9.2 项目约束

- 桌面 client **不写入** hui-agent Dockerfile，独立分发
- 代码位于 `repo/client/`
- 技术实现遵循 [技术方案](../solution/desktop-mcp-client.md)

### 9.3 外部依赖

- MCP Host：Cursor、Claude Desktop 或 hui-agent backend
- 同仓库 mousekey 项目可作为 capture / humanize 参考实现

---

## 10. 验收清单（Release Checklist）

### 10.1 功能验收

- [ ] 全部 P0 MCP Tools 在 Cursor 中可调用
- [ ] `get_recent_frames` 返回 50 帧 + 合法 manifest
- [ ] 鼠标移动无瞬移；点击坐标准确（±2px）
- [ ] 键盘输入与组合键在 macOS / Windows 各测 5 个用例
- [ ] 聊天框派发任务后 Agent 能驱动 MCP 完成桌面操作（场景 E）
- [ ] Socket Skill 连接并成功 `tool.invoke`（场景 G）
- [ ] 语音通话：STT 识别 + TTS 播报 + 口型动画（场景 F）

### 10.2 非功能验收

- [ ] 24h  soak test 通过
- [ ] 安装包在干净 VM（macOS / Windows 各一）安装成功
- [ ] 安全：HTTP 不绑定 0.0.0.0；临时目录权限正确

### 10.3 文档验收

- [ ] 用户安装指南（含权限步骤）
- [ ] Cursor MCP 配置说明
- [ ] 与技术方案、本 PRD 版本号一致

---

## 11. 风险与假设

### 11.1 假设

- 用户运行 MCP 的智能体 Host 与本机 client 在同一台机器（stdio 模式）
- 首期仅主显示器即可覆盖 80% 场景
- 用户接受 AI 控制键鼠前需明确授权

### 11.2 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| macOS 权限流程繁琐 | 安装转化低 | 分步引导 + 视频/GIF |
| Retina 坐标错位 | 点击失败 | manifest scale + E2E 校准 |
| 用户误触 AI 危险操作 | 数据丢失 | 危险键确认模式 |
| 帧目录占用磁盘 | 低配机器卡顿 | TTL + 环形缓冲 + 可选 JPEG |
| 浮层遮挡工作区 | 用户体验差 | 可折叠、调透明度、拖拽 |
| 语音识别误触发 | 错误任务 | 关键操作二次确认；Push-to-talk 可选 |
| Socket 端口冲突 | 连接失败 | 自动端口递增 + 设置页展示实际端口 |

---

## 12. 术语表

| 术语 | 说明 |
|------|------|
| MCP | Model Context Protocol，AI 工具调用标准协议 |
| stdio | MCP 通过标准输入输出与子进程通信 |
| 环形缓冲 | 固定 50 帧槽位，新帧覆盖最旧帧 |
| 逻辑坐标 | 与系统 API 一致的点坐标（非物理像素） |
| 物化 | 将内存/缓冲中的帧导出到临时目录供读取 |
| 数字人助手 | 桌面浮层中的虚拟形象，承载语音与情感反馈 |
| Socket Bridge | MCP 能力之上的本机 TCP 实时消息网关 |
| Vibe Coding | 用户自然语言描述需求，Agent 在指定目录自主完成编码 |
| TTS / STT | 文字转语音 / 语音转文字 |

---

## 13. 修订记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-07-26 | — | 初稿，对齐技术方案 v1.0 |
| v1.1 | 2026-07-26 | — | 新增桌面浮层、Socket Skill、语音通话需求 |
| v1.2 | 2026-07-26 | — | FR-10 TTS 优先 Edge TTS HTTP（tts-proxy） |
