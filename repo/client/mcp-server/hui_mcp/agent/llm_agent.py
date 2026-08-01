"""LLM-driven Agent — AI thinks and invokes MCP tools; Tauri is UI-only."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from hui_mcp.agent.llm_client import LlmClient, image_to_data_url
from hui_mcp.agent.llm_tools import openai_tool_definitions
from hui_mcp.agent.runtime import AgentResult, StepLog
from hui_mcp.config import AppConfig

log = logging.getLogger("hui_mcp.llm_agent")

ToolFn = Callable[[str, dict | None], dict]
ProgressFn = Callable[[str, str], None]

_SYSTEM = """你是 HuiAgent 桌面智能体，负责思考、规划与总结。
Companion/Tauri 只负责展示 UI；你必须通过工具控制本机桌面（截图、键鼠）。

阅读文档类任务建议流程：
1. get_screenshot 了解当前画面
2. keyboard_hotkey 打开查找（macOS: cmd+f，Windows: ctrl+f），keyboard_type 输入章节关键词
3. keyboard_press esc 关闭查找框，mouse_click 点击文档区域聚焦
4. 多次 keyboard_press page-down 滚屏，每次滚动后 get_screenshot
5. 阅读截图内容，用中文输出结构化摘要

约束：
- 必须真实调用工具，禁止编造未执行的操作
- 鼠标移动使用 mouse_move / mouse_click（平滑移动，不要要求瞬移）
- 滚屏优先 keyboard_press page-down
- 任务完成后给出清晰中文摘要，不要只返回工具 JSON
"""


class LlmAgent:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.client = LlmClient(cfg.llm)
        self.tools = openai_tool_definitions()

    def run(
        self,
        text: str,
        tool_fn: ToolFn,
        on_progress: ProgressFn | None = None,
    ) -> AgentResult:
        task_id = uuid.uuid4().hex[:10]
        steps: list[StepLog] = []

        def progress(step: str, message: str) -> None:
            steps.append(StepLog(step=step, message=message))
            if on_progress:
                on_progress(step, message)

        if not self.cfg.llm.ready():
            return AgentResult(
                task_id,
                False,
                "未配置 LLM API Key。请在 ~/.hui-agent/config.json 设置 llm.api_key，"
                "或 export HUI_AGENT_LLM_API_KEY=…\n"
                "也可在 Cursor 中接入 MCP（设置页导出配置），由 Cursor AI 直接调用桌面工具。",
                steps,
            )

        progress("plan", "LLM Agent 开始规划任务…")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text},
        ]

        screenshot_paths: list[str] = []
        max_steps = self.cfg.llm.max_steps

        for step_idx in range(max_steps):
            try:
                payload = self.client.chat(messages, tools=self.tools)
            except Exception as e:
                log.exception("llm chat failed")
                progress("error", str(e))
                return AgentResult(task_id, False, f"LLM 调用失败：{e}", steps)

            message = self.client.assistant_message(payload)
            calls = self.client.tool_calls(message)

            if not calls:
                reply = self.client.text_content(message)
                if not reply:
                    reply = "任务已结束，但未生成文本回复。"
                progress("done", "LLM 完成回复")
                return AgentResult(
                    task_id,
                    True,
                    reply,
                    steps,
                    {
                        "mode": "llm",
                        "model": self.cfg.llm.model,
                        "screenshots": screenshot_paths,
                        "llm_steps": step_idx + 1,
                    },
                )

            messages.append(message)

            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}

                progress("tool", f"调用 MCP 工具 {name}…")
                outcome = tool_fn(name, args)

                tool_text = LlmClient.dump_tool_result(name, outcome)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": tool_text,
                    }
                )

                if outcome.get("ok") and name == "get_screenshot":
                    result = outcome.get("result") or {}
                    path = result.get("path") if isinstance(result, dict) else None
                    if path:
                        screenshot_paths.append(str(path))
                        data_url = image_to_data_url(path)
                        if data_url:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"以上是工具 get_screenshot 返回的画面（{path}），请阅读并继续任务。",
                                        },
                                        {"type": "image_url", "image_url": {"url": data_url}},
                                    ],
                                }
                            )

        progress("error", "达到最大步数上限")
        return AgentResult(
            task_id,
            False,
            f"LLM Agent 在 {max_steps} 步内未完成任务，请简化指令或增大 llm.max_steps。",
            steps,
            {"mode": "llm", "screenshots": screenshot_paths},
        )
