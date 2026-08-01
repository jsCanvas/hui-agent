---
name: hui-agent-socket-bridge
description: 连接 HuiAgent Desktop 本机 Socket Bridge，实时调用 MCP 桌面能力（截屏、键鼠、语音）。在用户进行桌面自动化、阅读浏览器文档、vibe coding 或语音任务时使用。
---

# HuiAgent Socket Bridge Skill

通过 TCP 连接本机 HuiAgent Desktop 的 Socket Bridge，与 MCP 服务**实时双向交互**，适用于高频 tool 调用、帧流订阅、语音通话场景。

## 何时使用

- 用户已通过 HuiAgent Desktop 启动应用，需要 Agent **实时**操作桌面
- 用户说 **「连接 socket」** → 使用 [`hui-agent-cursor-relay`](../hui-agent-cursor-relay/SKILL.md) 一键启动 `connect-cursor-socket.sh`
- 任务涉及连续滚动、多步键鼠、观察界面变化（如「阅读浏览器第三节」）
- 语音通话模式：需 `tts_speak` / STT 事件
- stdio MCP 延迟过高或需要 Server Push（`frame.push`、`task.progress`）

## 前置条件

1. 本机已安装并运行 **HuiAgent Desktop**
2. MCP 服务状态为「运行中」
3. 读取配置文件获取连接信息：

```bash
cat ~/.hui-agent/config.json
```

示例：

```json
{
  "socket": { "host": "127.0.0.1", "port": 18765, "token": "YOUR_TOKEN" },
  "mcp": { "stdio_command": "..." }
}
```

## 连接流程

### 1. 建立 TCP 连接

```
host: 127.0.0.1
port: 18765（若占用，见 config 实际 port）
protocol: NDJSON（每行一个 JSON 对象，UTF-8）
```

### 2. 鉴权（首条消息）

```json
{"type":"auth","token":"YOUR_TOKEN"}
```

期望响应：

```json
{"type":"auth.ok","session_id":"..."}
```

失败：

```json
{"type":"auth.fail","code":"INVALID_TOKEN","message":"..."}
```

### 3. 心跳

每 15 秒发送：

```json
{"type":"ping"}
```

期望：`{"type":"pong"}`

## 核心操作

### 调用 MCP Tool

```json
{"type":"tool.invoke","id":"unique-id-1","name":"mouse_scroll","arguments":{"dy":-5}}
```

响应：

```json
{"type":"tool.result","id":"unique-id-1","ok":true,"result":{}}
```

错误：

```json
{"type":"tool.result","id":"unique-id-1","ok":false,"error":{"code":"PERMISSION_DENIED","message":"..."}}
```

### 可用 Tool 名称

与 MCP 一致，包括但不限于：

| name | 用途 |
|------|------|
| `get_recent_frames` | 最近 5s/50 帧 |
| `get_screenshot` | 当前截图 |
| `get_screen_info` | 屏幕参数 |
| `mouse_move` / `mouse_click` / `mouse_scroll` / `mouse_drag` | 鼠标 |
| `keyboard_press` / `keyboard_hotkey` / `keyboard_type` | 键盘 |
| `tts_speak` / `tts_stop` / `stt_listen` | 语音（TTS 默认 Edge HTTP :8896） |
| `voice_call_start` / `voice_call_stop` | 通话模式 |

### 订阅帧推送

```json
{"type":"frame.subscribe","fps":2}
```

服务端推送：

```json
{"type":"frame.push","path":"/tmp/hui-agent-frames-xxx/frame_000042.png","timestamp_ms":1719305123456}
```

### 发送聊天消息（触发内置 Agent）

```json
{"type":"chat.send","text":"阅读桌面浏览器网页上的 XX 需求文档的第三节"}
```

流式回复：

```json
{"type":"chat.delta","text":"正在定位浏览器窗口…"}
{"type":"chat.done","message_id":"..."}
```

### 任务进度

```json
{"type":"task.progress","task_id":"t1","step":"scroll","message":"正在滚动至第三节…"}
{"type":"task.complete","task_id":"t1","summary":"第三节摘要：…"}
```

## 推荐工作流

### 工作流 A：阅读浏览器指定章节

```
1. tool.invoke → get_screenshot
2. tool.invoke → get_recent_frames
3. 分析画面，定位浏览器与文档结构
4. loop:
     tool.invoke → mouse_scroll { dy: -3 }
     tool.invoke → get_screenshot
     直到 OCR/VLM 确认「第三节」可见
5. 生成摘要，chat.delta 或直接回复用户
```

### 工作流 B：语音 Vibe Coding

```
1. tool.invoke → voice_call_start
2. 监听 voice.stt.final
3. 解析：需求来源（文档第三节）、接口规范、目标目录
4. tool.invoke → tts_speak { text, voice: "zh-CN-XiaoxiaoNeural", rate: "+5%" }
5. 收到确认后：
     - keyboard_hotkey 打开终端/IDE
     - keyboard_type 执行命令
     - 或通过 chat.send 触发内置 coding agent
6. 各阶段 task.progress + tts_speak 播报
7. tool.invoke → voice_call_stop
```

## Python 连接示例

```python
import json
import socket
from pathlib import Path

cfg = json.loads(Path("~/.hui-agent/config.json").expanduser().read_text())
host, port = cfg["socket"]["host"], cfg["socket"]["port"]
token = cfg["socket"]["token"]

def send(sock, obj):
    sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode())

def recv_line(sock):
    buf = b""
    while not buf.endswith(b"\n"):
        buf += sock.recv(1)
    return json.loads(buf.decode())

with socket.create_connection((host, port), timeout=5) as s:
    send(s, {"type": "auth", "token": token})
    assert recv_line(s)["type"] == "auth.ok"

    send(s, {"type": "tool.invoke", "id": "1", "name": "get_screenshot", "arguments": {}})
    result = recv_line(s)
    print(result)
```

## 错误码

| code | 含义 | 处理 |
|------|------|------|
| `INVALID_TOKEN` | 鉴权失败 | 检查 config.json |
| `PERMISSION_DENIED` | 缺少屏幕/辅助功能/麦克风 | 提示用户在 HuiAgent 完成授权 |
| `TOOL_NOT_FOUND` | 未知 tool | 检查 name 拼写 |
| `TOOL_BUSY` | 键鼠操作进行中 | 等待后重试 |
| `CONNECTION_CLOSED` | 服务已停止 | 提示用户启动 HuiAgent Desktop |

## 重连策略

1. 连接失败：等待 2s，最多重试 5 次
2. 运行中断线：重新 auth；已进行的 task 向用户说明需重新派发
3. 切勿在未 auth 成功前发送 `tool.invoke`

## 安全约束

- 仅连接 `127.0.0.1`，不要暴露到公网
- Token 不要写入日志或提交到 Git
- 危险操作（删除文件、cmd+q）前必须用户确认

## 相关文档

- [PRD](../../../prd/desktop-mcp-client.md)
- [技术方案](../../desktop-mcp-client.md) §4.5、§4.6
- [Edge TTS 集成](../../edge-tts-integration.md)
