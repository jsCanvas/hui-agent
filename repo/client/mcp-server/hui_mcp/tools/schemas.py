"""MCP tool JSON schemas."""

from __future__ import annotations

import mcp.types as types

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_recent_frames",
        description="获取最近 5 秒桌面逐帧截图（10fps），写入临时目录并返回 manifest",
        inputSchema={"type": "object", "properties": {"monitor": {"type": "integer", "default": 0}}},
    ),
    types.Tool(
        name="get_screenshot",
        description="获取当前桌面单帧截图",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_screen_info",
        description="获取主屏分辨率与 scale",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="check_permissions",
        description="检测屏幕/辅助功能/Edge TTS 权限与服务状态",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="activate_document_app",
        description="将浏览器或文档 App 切到前台（跳过 Cursor/HuiAgent）。文档阅读任务中由 Cursor 总指挥调用",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="activate_cursor_app",
        description="将 Cursor IDE 切到前台。写摘要前可选调用",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="mouse_get_position",
        description="获取当前鼠标逻辑坐标",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="mouse_move",
        description="平滑移动鼠标（贝塞尔曲线，步数随距离自适应）",
        inputSchema={
            "type": "object",
            "required": ["x", "y"],
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "steps": {"type": "integer"},
                "fast": {"type": "boolean", "default": False},
            },
        },
    ),
    types.Tool(
        name="mouse_click",
        description="平滑移动后点击",
        inputSchema={
            "type": "object",
            "required": ["x", "y"],
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "clicks": {"type": "integer", "default": 1},
                "fast": {"type": "boolean", "default": False},
            },
        },
    ),
    types.Tool(
        name="mouse_drag",
        description="平滑拖拽",
        inputSchema={
            "type": "object",
            "required": ["x1", "y1", "x2", "y2"],
            "properties": {
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
            },
        },
    ),
    types.Tool(
        name="mouse_scroll",
        description=(
            "滚轮小步滚动（阅读模式：|dy|≤24，拆成 12 步；禁止 Page Down 补滚）。"
            "传 x,y 先点击文档区（约 width×0.32, height×0.42）再滚；"
            "dy<0 向下，dy>0 向上；用于把待读段落微调到屏幕中央。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "dx": {"type": "integer"},
                "dy": {"type": "integer"},
                "x": {"type": "integer", "description": "滚动前先点击的文档 X（逻辑坐标）"},
                "y": {"type": "integer", "description": "滚动前先点击的文档 Y（逻辑坐标）"},
            },
        },
    ),
    types.Tool(
        name="keyboard_press",
        description="按下单键",
        inputSchema={
            "type": "object",
            "required": ["key"],
            "properties": {"key": {"type": "string"}},
        },
    ),
    types.Tool(
        name="keyboard_hotkey",
        description="组合键",
        inputSchema={
            "type": "object",
            "required": ["keys"],
            "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
        },
    ),
    types.Tool(
        name="keyboard_type",
        description="输入文本（≤500 字）",
        inputSchema={
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
    ),
    types.Tool(
        name="tts_speak",
        description="Edge TTS 拟人语音播报（默认晓晓音色）",
        inputSchema={
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "voice": {"type": "string"},
                "rate": {"type": "string"},
                "pitch": {"type": "string"},
                "volume": {"type": "string"},
            },
        },
    ),
    types.Tool(
        name="tts_stop",
        description="停止当前 TTS 播放",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="stt_listen",
        description="语音识别（一次）",
        inputSchema={
            "type": "object",
            "properties": {"timeout_ms": {"type": "integer"}, "language": {"type": "string"}},
        },
    ),
    types.Tool(
        name="voice_call_start",
        description="开启语音通话模式（STT → Agent → TTS）",
        inputSchema={
            "type": "object",
            "properties": {
                "background_listen": {
                    "type": "boolean",
                    "description": "后台麦克风监听（Companion 用 Web Speech 时可 false）",
                }
            },
        },
    ),
    types.Tool(
        name="voice_call_stop",
        description="结束语音通话模式",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="companion_connection_status",
        description="查询 Cursor Socket 连接与监听状态（cursor_online、watch 剩余时间）",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="companion_socket_connect",
        description=(
            "后台启动 Socket 连接（detached 进程，不切 Cursor 前台），默认监听 12 小时（720 分钟）。"
            "提前停止须手动调用 companion_socket_disconnect。"
            "连接成功后默认再 waiting 12 小时（与 watch 一致）；收到任务仅系统通知 + pending，禁止 osascript 激活 Cursor。"
            "若 continue_waiting 为 true，循环调用 companion_socket_wait。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "watch_minutes": {
                    "type": "number",
                    "default": 720,
                    "description": "监听时长（分钟），默认 720（12 小时）；提前停止请 companion_socket_disconnect",
                },
                "wait_timeout_sec": {
                    "type": "number",
                    "default": 43200,
                    "description": "连接成功后本轮 waiting 秒数（默认 43200=12h，与 watch 一致；0=仅连接不等待）",
                },
            },
        },
    ),
    types.Tool(
        name="companion_socket_connect_and_wait",
        description=(
            "一键：若 cursor_online 为 false 则后台连接 Socket（默认 12 小时监听，不切 Cursor 前台），"
            "随后立即执行 companion_socket_wait 进入任务监听；Companion 显示「监听中」。"
            "用户说「连接 socket」时优先调用本工具；task_received 后 companion_task_pending 处理任务；"
            "companion_task_complete 默认 auto_wait=true 会自动进入下一轮 companion_socket_wait；"
            "若 wait 返回 continue_waiting 或 poll_timeout，再调 companion_socket_wait 或本工具。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "watch_minutes": {
                    "type": "number",
                    "default": 720,
                    "description": "连接时监听时长（分钟），默认 720（12 小时）",
                },
                "timeout_sec": {
                    "type": "number",
                    "default": 43200,
                    "description": "本轮 companion_socket_wait 最长秒数（默认 43200=12h）",
                },
                "poll_interval_sec": {
                    "type": "number",
                    "default": 2,
                    "description": "轮询 pending 间隔秒数",
                },
            },
        },
    ),
    types.Tool(
        name="companion_socket_wait",
        description=(
            "在 Socket 已连接时 waiting 任务通知（轮询 pending，不切 Cursor 前台）。"
            "task_received 后处理任务；continue_waiting 则再次调用本工具。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "timeout_sec": {
                    "type": "number",
                    "default": 43200,
                    "description": "本轮最长等待秒数（默认 43200=12h，与 Socket 监听一致；不超过 watch 剩余时间）",
                },
                "poll_interval_sec": {
                    "type": "number",
                    "default": 2,
                    "description": "轮询间隔秒数",
                },
            },
        },
    ),
    types.Tool(
        name="companion_socket_disconnect",
        description="手动停止 Cursor Socket 后台监听进程（提前结束监听的唯一方式）",
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "无法正常退出时强制 kill",
                },
            },
        },
    ),
    types.Tool(
        name="companion_task_pending",
        description="获取 Companion 待处理任务：文字 task（pending）与通话 utterance（voice_pending）",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="companion_speak",
        description="经 Socket 让 Companion 播报语音（Live2D 口型同步）。可多次调用实现流式分段播报。",
        inputSchema={
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "要播报的中文文本"},
                "utterance_id": {
                    "type": "string",
                    "description": "关联的 voice utterance_id（来自 voice_pending）",
                },
                "final": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否为该段的最后一段播报",
                },
                "interrupt": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否打断当前 Companion TTS",
                },
            },
        },
    ),
    types.Tool(
        name="companion_doc_read_start",
        description=(
            "（Legacy）启动 Daemon 后台 OCR Worker。"
            "默认已禁用 auto_start_on_relay；文档阅读改由 Cursor Agent 用 "
            "get_screenshot + 键鼠 MCP 主动读屏。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "任务 ID；省略则用当前 pending",
                },
                "text": {
                    "type": "string",
                    "description": "任务原文；省略则从 pending 读取",
                },
            },
        },
    ),
    types.Tool(
        name="companion_doc_read_status",
        description=(
            "（Legacy）查询后台 OCR Worker 进度。"
            "Agent 主动读屏模式下勿用；改用 get_screenshot + Read 截图。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "任务 ID；省略则用当前 pending",
                },
                "full_ocr": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否返回完整 ocr_text（较长文档可设 false 仅看 preview）",
                },
            },
        },
    ),
    types.Tool(
        name="companion_task_complete",
        description=(
            "提交 Companion 任务结果。文字任务用 task_id；通话轮次用 utterance_id + channel=voice。"
            "默认 auto_wait=true：成功后自动执行 companion_socket_wait 进入监听（禁止自动 disconnect）；"
            "若 wait 返回 task_received 则 agent_next=companion_task_pending。"
        ),
        inputSchema={
            "type": "object",
            "required": ["reply"],
            "properties": {
                "task_id": {"type": "string", "description": "文字任务 ID"},
                "utterance_id": {"type": "string", "description": "通话 utterance ID"},
                "reply": {"type": "string"},
                "ok": {"type": "boolean", "default": True},
                "auto_wait": {
                    "type": "boolean",
                    "default": True,
                    "description": "提交成功后是否立即 companion_socket_wait（默认 true）",
                },
                "timeout_sec": {
                    "type": "number",
                    "default": 43200,
                    "description": "auto_wait 时本轮 companion_socket_wait 最长秒数",
                },
                "poll_interval_sec": {
                    "type": "number",
                    "default": 2,
                    "description": "auto_wait 时轮询 pending 间隔秒数",
                },
                "channel": {
                    "type": "string",
                    "enum": ["text", "voice"],
                    "description": "voice 时优先完成通话轮次",
                },
            },
        },
    ),
]
