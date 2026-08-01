"""Agent Runtime — orchestrates MCP tools from natural language tasks."""

from __future__ import annotations

import json
import platform
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from hui_mcp.agent.intents import Intent, IntentKind, classify
from hui_mcp.agent.read_section_flow import build_summary, scroll_capture_pages, search_section
from hui_mcp.context import AppContext
from hui_mcp.tools.registry import invoke_tool

ProgressCallback = Callable[[str, str, str], None]

INPUT_TOOLS = frozenset(
    {
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_press",
        "keyboard_hotkey",
        "keyboard_type",
        "tts_speak",
        "tts_stop",
    }
)


@dataclass
class StepLog:
    step: str
    message: str


@dataclass
class AgentResult:
    task_id: str
    ok: bool
    reply: str
    steps: list[StepLog] = field(default_factory=list)
    data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "ok": self.ok,
            "reply": self.reply,
            "steps": [asdict(s) for s in self.steps],
            "data": self.data,
        }


class AgentRuntime:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._lock = threading.Lock()

    @staticmethod
    def _compose_task_text(
        text: str,
        image_paths: list[str] | None,
        file_paths: list[str] | None = None,
    ) -> str:
        trimmed = text.strip()
        attachments: list[str] = []
        for p in [x.strip() for x in (file_paths or []) if x.strip()]:
            attachments.append(f"[工作区文件: {p}]")
        for p in [x.strip() for x in (image_paths or []) if x.strip()]:
            attachments.append(f"[用户上传图片: {p}]")

        body = trimmed
        if attachments:
            ctx = "\n".join(attachments)
            vibe = (
                "请结合以上 @ 引用的工作区文件与图片，在当前项目上下文中分析并协助 vibe coding。"
            )
            body = f"{trimmed}\n\n{ctx}\n\n{vibe}" if trimmed else f"{ctx}\n\n{vibe}"
        return body

    def run(
        self,
        text: str,
        on_progress: ProgressCallback | None = None,
        *,
        image_paths: list[str] | None = None,
        file_paths: list[str] | None = None,
    ) -> AgentResult:
        task_id = uuid.uuid4().hex[:10]
        steps: list[StepLog] = []
        full_text = self._compose_task_text(text, image_paths, file_paths)

        def progress(step: str, message: str) -> None:
            steps.append(StepLog(step=step, message=message))
            if on_progress:
                on_progress(task_id, step, message)

        if self.ctx.config.effective_agent_mode() == "cursor":
            from hui_mcp.cursor_relay import get_relay

            progress("relay", "等待 Cursor MCP 处理 Companion 任务…")

            def relay_progress(rid: str, step: str, message: str) -> None:
                if on_progress:
                    on_progress(rid, step, message)

            outcome = get_relay().run_task(full_text, relay_progress)
            relay_steps = [StepLog(**s) for s in outcome.get("steps", [])]
            return AgentResult(
                outcome["task_id"],
                outcome["ok"],
                outcome["reply"],
                relay_steps or steps,
                outcome.get("data"),
            )

        if self.ctx.config.effective_agent_mode() == "llm":
            from hui_mcp.agent.llm_agent import LlmAgent

            progress("plan", "LLM Agent：AI 思考 + MCP 操控桌面")
            return LlmAgent(self.ctx.config).run(full_text, self._tool, progress)

        intent = classify(full_text)
        progress("plan", f"识别任务类型：{intent.kind.value}")

        try:
            if intent.kind == IntentKind.READ_DOC_SECTION:
                return self._read_doc_section(task_id, intent, progress, steps)
            if intent.kind == IntentKind.READ_DOC_SECTION_FULL:
                return self._read_doc_section_full(task_id, intent, progress, steps)
            if intent.kind == IntentKind.SCROLL_DOWN:
                return self._scroll(task_id, -intent.scroll_amount, progress, steps)
            if intent.kind == IntentKind.SCROLL_UP:
                return self._scroll(task_id, intent.scroll_amount, progress, steps)
            if intent.kind == IntentKind.SCREENSHOT:
                return self._screenshot(task_id, progress, steps)
            if intent.kind == IntentKind.CHECK_PERMISSIONS:
                return self._check_permissions(task_id, progress, steps)
            if intent.kind == IntentKind.HELP:
                return self._help(task_id, steps)
            return self._unknown(task_id, text, steps)
        except Exception as e:
            progress("error", str(e))
            return AgentResult(
                task_id=task_id,
                ok=False,
                reply=f"任务执行失败：{e}",
                steps=steps,
            )

    def _tool(self, name: str, arguments: dict | None = None) -> dict:
        if name in INPUT_TOOLS:
            with self._lock:
                return invoke_tool(self.ctx, name, arguments or {})
        return invoke_tool(self.ctx, name, arguments or {})

    def _read_doc_section(
        self,
        task_id: str,
        intent: Intent,
        progress: Callable[[str, str], None],
        steps: list[StepLog],
    ) -> AgentResult:
        query = intent.section_query or "第三节"
        progress("screenshot", "获取当前屏幕画面…")
        shot = self._tool("get_screenshot")
        if not shot.get("ok"):
            return AgentResult(task_id, False, f"截屏失败：{shot.get('error')}", steps)

        progress("search", f"在页面中搜索「{query}」…")
        mod = "cmd" if platform.system() == "Darwin" else "ctrl"
        for call in (
            ("keyboard_hotkey", {"keys": [mod, "f"]}),
            ("keyboard_type", {"text": query}),
            ("keyboard_press", {"key": "enter"}),
        ):
            out = self._tool(call[0], call[1])
            if not out.get("ok"):
                return AgentResult(
                    task_id,
                    False,
                    f"键盘操作失败（{call[0]}）：{out.get('error')}",
                    steps,
                )
        time.sleep(0.6)

        progress("focus", "关闭查找框并聚焦页面…")
        from hui_mcp.agent.read_section_flow import dismiss_search_and_focus

        dismiss_search_and_focus(self._tool, progress)

        progress("capture", "搜索完成，采集最新画面…")
        shot2 = self._tool("get_screenshot")
        frames = self._tool("get_recent_frames")
        data = {
            "search_query": query,
            "screenshot_before": _result_path(shot),
            "screenshot_after": _result_path(shot2),
            "recent_frames": _result_path(frames, key="directory"),
        }
        progress("done", "已完成定位流程")
        reply = (
            f"已在当前页面搜索「{query}」。\n"
            f"- 搜索前截图：{data.get('screenshot_before') or '—'}\n"
            f"- 搜索后截图：{data.get('screenshot_after') or '—'}\n"
            f"- 最近 5 秒帧目录：{data.get('recent_frames') or '—'}\n"
            "如需继续阅读，可让我「向下滚动」或指定其他章节。"
        )
        return AgentResult(task_id, True, reply, steps, data)

    def _read_doc_section_full(
        self,
        task_id: str,
        intent: Intent,
        progress: Callable[[str, str], None],
        steps: list[StepLog],
    ) -> AgentResult:
        query = intent.section_query or "第三节"
        ok, err = search_section(self._tool, query, progress)
        if not ok:
            return AgentResult(task_id, False, err or "搜索失败", steps)

        progress("capture", "定位完成，开始自动滚动阅读…")
        dr = self.ctx.config.doc_read
        pages = scroll_capture_pages(
            self._tool,
            progress,
            section_query=query,
            max_pages=dr.max_pages,
            page_downs=dr.page_downs,
            scroll_dy=dr.scroll_dy,
            stale_hits_to_stop=dr.stale_hits_to_stop,
        )
        if not pages:
            shot = self._tool("get_screenshot")
            p = _result_path(shot)
            if p:
                pages = [p]

        progress("summarize", "整理 OCR 文本并生成摘要…")
        summary, full_ocr, snippets = build_summary(query, pages)
        frames = self._tool("get_recent_frames")
        data = {
            "search_query": query,
            "pages": pages,
            "page_count": len(pages),
            "ocr_text": full_ocr,
            "ocr_snippets": snippets,
            "recent_frames": _result_path(frames, key="directory"),
        }
        progress("done", f"已完成滚动阅读，共 {len(pages)} 屏")
        return AgentResult(task_id, True, summary, steps, data)

    def _scroll(
        self,
        task_id: str,
        dy: int,
        progress: Callable[[str, str], None],
        steps: list[StepLog],
    ) -> AgentResult:
        progress("scroll", f"平滑滚动页面（dy={dy}）…")
        loops = 3
        for i in range(loops):
            out = self._tool("mouse_scroll", {"dy": dy})
            if not out.get("ok"):
                return AgentResult(task_id, False, f"滚动失败：{out.get('error')}", steps)
            time.sleep(0.25)
        shot = self._tool("get_screenshot")
        path = _result_path(shot)
        progress("done", "滚动完成")
        direction = "下" if dy < 0 else "上"
        return AgentResult(
            task_id,
            True,
            f"已向{direction}滚动 {loops} 次。当前截图：{path or '—'}",
            steps,
            {"screenshot": path, "dy": dy, "loops": loops},
        )

    def _screenshot(
        self,
        task_id: str,
        progress: Callable[[str, str], None],
        steps: list[StepLog],
    ) -> AgentResult:
        progress("screenshot", "正在截取当前屏幕…")
        out = self._tool("get_screenshot")
        if not out.get("ok"):
            return AgentResult(task_id, False, f"截屏失败：{out.get('error')}", steps)
        path = _result_path(out)
        info = self._tool("get_screen_info")
        progress("done", "截屏完成")
        w = h = "?"
        if info.get("ok") and info.get("result"):
            w = info["result"].get("width", "?")
            h = info["result"].get("height", "?")
        return AgentResult(
            task_id,
            True,
            f"已截取当前屏幕（{w}×{h}）。文件：{path}",
            steps,
            {"screenshot": path, "screen": info.get("result")},
        )

    def _check_permissions(
        self,
        task_id: str,
        progress: Callable[[str, str], None],
        steps: list[StepLog],
    ) -> AgentResult:
        progress("check", "检测系统权限与服务…")
        out = self._tool("check_permissions")
        if not out.get("ok"):
            return AgentResult(task_id, False, f"检测失败：{out.get('error')}", steps)
        perms = out.get("result", {}).get("permissions", [])
        lines = []
        for p in perms:
            mark = "✅" if p.get("ok") else "❌"
            hint = f"（{p['hint']}）" if p.get("hint") else ""
            lines.append(f"{mark} {p.get('name')}{hint}")
        progress("done", "检测完成")
        return AgentResult(task_id, True, "权限与服务状态：\n" + "\n".join(lines), steps, out.get("result"))

    def _help(self, task_id: str, steps: list[StepLog]) -> AgentResult:
        reply = (
            "我可以帮你执行以下桌面任务（直接说即可）：\n"
            "1. 「阅读浏览器需求文档第三节」→ 页面内搜索并截帧\n"
            "2. 「完整阅读第四节并总结」→ Worker 滚屏+OCR；Cursor 读 pages 截图+ocr_text 总结（edge_outline 仅参考）\n"
            "3. 「向下滚动 / 向上滚动」→ 平滑滚轮 + 截图\n"
            "3. 「截屏 / 看一下当前画面」→ 获取截图路径\n"
            "4. 「检查权限」→ 屏幕录制 / 辅助功能 / Edge TTS\n"
            "复杂任务也可通过 Socket `tool.invoke` 精确调用 MCP 工具。"
        )
        return AgentResult(task_id, True, reply, steps)

    def _unknown(self, task_id: str, text: str, steps: list[StepLog]) -> AgentResult:
        reply = (
            f"我还不能完全理解：「{text}」。\n"
            "你可以试试：\n"
            "• 阅读桌面浏览器网页上的需求文档第三节\n"
            "• 向下滚动页面\n"
            "• 截屏\n"
            "• 检查权限\n"
            "或输入「帮助」查看能力列表。"
        )
        return AgentResult(task_id, False, reply, steps)


def _result_path(outcome: dict, key: str = "path") -> str | None:
    if not outcome.get("ok"):
        return None
    result = outcome.get("result")
    if isinstance(result, dict):
        return result.get(key) or result.get("directory")
    return None
