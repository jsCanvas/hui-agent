---
name: hui-agent-cursor-relay
description: >-
  一键启动 HuiAgent Cursor Socket Relay（cursor-socket-client.py）。
  在用户说「连接 socket」「启动 cursor relay」「cursor socket 连接」、
  Companion 任务需要 cursor_online、或 health 显示 cursor_online false 时使用。
---

# HuiAgent Cursor Socket Relay

Companion / 通话模式任务需要 **Cursor 经 Socket 长连接** 才能 relay。本技能用于在 Cursor 输入框一句话启动连接。

## 触发语（用户可能说）

- 连接 socket / 连接 Socket Relay
- 启动 cursor-socket-client / cursor relay
- cursor_online 是 false，帮我连上
- 一键 socket 连接

## Agent 必须执行的步骤

1. **检查 Daemon**（需 `npm run dev` 已运行）：

```bash
curl -sf http://127.0.0.1:18766/health | python3 -m json.tool
```

若 unreachable → 提示用户先 `cd hui-agent/repo/client && npm run dev`。

2. **一键连接**（优先用脚本，勿让用户手敲长命令）：

```bash
cd hui-agent/repo/client
chmod +x scripts/connect-cursor-socket.sh
./scripts/connect-cursor-socket.sh
```

若用户需要看实时日志（调试）：

```bash
./scripts/connect-cursor-socket.sh --foreground
```

或在单独终端后台保持：

```bash
python3 scripts/cursor-socket-client.py
```

3. **验证成功**：

```bash
curl -sf http://127.0.0.1:18766/health | python3 -c \
  "import json,sys; d=json.load(sys.stdin); a=d['agent']; print('cursor_online:', a['cursor_online']); print('companion_online:', a.get('companion_online'))"
```

期望：`cursor_online: True`。Companion 通话还需 `companion_online: True`（`npm run dev` 启动后自动连）。

4. **向用户汇报**：连接状态 + 若失败则 `tail ~/.hui-agent/cursor-socket.log`。

## 架构速记

```
Companion / 通话 STT
  → Socket Bridge :18765
  → cursor-socket-client.py（role=cursor）
  → Cursor AI（MCP 大脑）
  → companion_speak / companion_task_complete
```

## 常见问题

| 现象 | 处理 |
|------|------|
| Connection refused | 先 `npm run dev` |
| CURSOR_BUSY | 已有 relay 连接；查 health，通常无需再起第二个 |
| cursor_online false 但进程在跑 | 等 5s 重试 health；或 kill 旧进程后 `./scripts/connect-cursor-socket.sh` |

## 相关

- 脚本：`hui-agent/repo/client/scripts/connect-cursor-socket.sh`
- Relay 客户端：`hui-agent/repo/client/scripts/cursor-socket-client.py`
- 使用说明：`hui-agent/docs/prd/companion-usage.md`
- Socket 协议：`hui-agent/docs/solution/skills/hui-agent-socket-bridge/SKILL.md`
