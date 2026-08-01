"""Relay Companion tasks to Cursor (via socket + MCP), no Cursor SDK."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from hui_mcp.active_task_store import clear_active_task, read_active_task

ProgressFn = Callable[[str, str, str], None]


@dataclass
class RelayTask:
    task_id: str
    text: str
    done: threading.Event = field(default_factory=threading.Event)
    ok: bool = False
    reply: str = ""
    steps: list[dict[str, str]] = field(default_factory=list)
    data: dict[str, Any] | None = None


class CursorRelay:
    """Thread-safe bridge between Companion and Cursor MCP session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cursor_online = False
        self._active: RelayTask | None = None
        self._notify_cursor: Callable[[RelayTask], None] | None = None
        self._ctx: Any = None
        self._runtime: Any = None

    def set_worker_deps(self, ctx: Any, runtime: Any) -> None:
        """Inject daemon context for background OCR worker."""
        self._ctx = ctx
        self._runtime = runtime
        from hui_mcp.agent.doc_read_worker import get_doc_read_worker

        get_doc_read_worker().set_deps(ctx, runtime)

    def set_notify(self, fn: Callable[[RelayTask], None] | None) -> None:
        self._notify_cursor = fn

    def set_cursor_online(self, online: bool) -> None:
        with self._lock:
            self._cursor_online = online

    def is_cursor_online(self) -> bool:
        with self._lock:
            return self._cursor_online

    def get_pending(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active and not self._active.done.is_set():
                return {"task_id": self._active.task_id, "text": self._active.text}
            return None

    def run_task(
        self,
        text: str,
        on_progress: ProgressFn | None = None,
        *,
        timeout_sec: float = 600,
    ) -> dict[str, Any]:
        """Block until Cursor MCP completes the task via companion_task_complete."""
        if not self.is_cursor_online():
            return {
                "ok": False,
                "reply": (
                    "Cursor 未通过 Socket 连接。\n\n"
                    "请在 Cursor Agent 中调用 companion_socket_connect 启动 12 小时监听，"
                    "或运行 scripts/cursor-socket-client.py --watch-minutes 720。"
                    "提前停止请 companion_socket_disconnect。"
                ),
                "steps": [{"step": "error", "message": "cursor socket offline"}],
                "task_id": uuid.uuid4().hex[:10],
            }

        task = RelayTask(task_id=uuid.uuid4().hex[:10], text=text.strip())
        with self._lock:
            if self._active and not self._active.done.is_set():
                return {
                    "ok": False,
                    "reply": "已有任务在处理中，请稍候。",
                    "steps": [],
                    "task_id": task.task_id,
                }
            self._active = task

        from hui_mcp.task_cancel import get_task_cancel

        get_task_cancel().begin(task.task_id)

        from hui_mcp.agent.doc_read_worker import get_doc_read_worker, is_doc_read_task

        is_doc, _section = is_doc_read_task(task.text)
        worker = get_doc_read_worker()

        if is_doc and self._ctx and self._ctx.config.doc_read.auto_start_on_relay:
            worker.maybe_start(task, on_progress)
            if on_progress:
                on_progress(
                    task.task_id,
                    "doc_read",
                    "已在当前前台页面启动 OCR Worker（不切换窗口）",
                )

        if on_progress:
            trigger_mode = (
                self._ctx.config.doc_read.cursor_trigger if self._ctx else "notify"
            )
            if is_doc:
                auto_worker = (
                    self._ctx
                    and self._ctx.config.doc_read.auto_start_on_relay
                )
                if auto_worker:
                    mode = (
                        "文档前台 OCR Worker 已启动（legacy）；Cursor 后台触发"
                        if trigger_mode in ("notify", "background", "notify_only")
                        else "已通过 Socket 通知 Cursor"
                    )
                else:
                    mode = (
                        "文档阅读交给 Cursor Agent（get_screenshot + 键鼠工具，无 OCR Worker）"
                        if trigger_mode in ("notify", "background", "notify_only")
                        else "已通过 Socket 通知 Cursor 主动读屏"
                    )
            else:
                mode = "后台 Socket 已连接；Agent 请 companion_socket_wait（不切前台）"
            on_progress(task.task_id, "relay", mode)
        if self._notify_cursor:
            try:
                self._notify_cursor(task)
            except Exception as e:
                with self._lock:
                    self._active = None
                return {
                    "ok": False,
                    "reply": f"通知 Cursor 失败：{e}",
                    "steps": [],
                    "task_id": task.task_id,
                }
        else:
            with self._lock:
                self._active = None
            return {
                "ok": False,
                "reply": "Socket Bridge 未就绪，无法通知 Cursor。请重启 npm run dev。",
                "steps": [{"step": "error", "message": "notify unavailable"}],
                "task_id": task.task_id,
            }

        if on_progress:
            wait_msg = (
                "等待 Cursor Agent 读屏写摘要（get_screenshot + 键鼠工具）…"
                if is_doc
                and not (
                    self._ctx and self._ctx.config.doc_read.auto_start_on_relay
                )
                else (
                    "OCR Worker 进行中；Cursor 轮询 companion_doc_read_status → 总结"
                    if is_doc
                    else "等待 Cursor AI 处理…"
                )
            )
            on_progress(task.task_id, "wait", wait_msg)

        if not task.done.wait(timeout=timeout_sec):
            with self._lock:
                if self._active is task:
                    self._active = None
            return {
                "ok": False,
                "reply": (
                    f"等待 Cursor AI 超时（{int(timeout_sec)}s）。"
                    "任务仍保留在 pending；请在 Cursor 中继续处理并调用 companion_task_complete。"
                ),
                "steps": [{"step": "error", "message": "timeout"}],
                "task_id": task.task_id,
            }

        return {
            "ok": task.ok,
            "reply": task.reply,
            "steps": task.steps,
            "task_id": task.task_id,
            "data": task.data,
        }

    def complete_task(
        self,
        task_id: str,
        *,
        reply: str,
        ok: bool = True,
        steps: list[dict[str, str]] | None = None,
        data: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            if self._active and self._active.task_id == task_id:
                self._active.ok = ok
                self._active.reply = reply
                self._active.steps = steps or []
                self._active.data = data
                self._active.done.set()
                self._active = None
                clear_active_task()
                from hui_mcp.agent.doc_read_store import get_doc_read_store

                get_doc_read_store().clear(task_id)
                if self._ctx and self._ctx.config.doc_read.notify_on_complete and ok:
                    from hui_mcp.notify import macos_notify

                    preview = (reply or "")[:100].replace("\n", " ")
                    macos_notify("Companion 任务完成", task_id[:8], preview)
                from hui_mcp.task_cancel import get_task_cancel

                get_task_cancel().clear()
                from hui_mcp.automation_consent import clear_automation_grant

                clear_automation_grant(task_id)
                return True
            stale = read_active_task()
            if stale and stale.get("task_id") == task_id:
                clear_active_task()
                from hui_mcp.agent.doc_read_store import get_doc_read_store

                get_doc_read_store().clear(task_id)
                if self._ctx and self._ctx.config.doc_read.notify_on_complete and ok:
                    from hui_mcp.notify import macos_notify

                    preview = (reply or "")[:100].replace("\n", " ")
                    macos_notify("Companion 任务完成", task_id[:8], preview)
                from hui_mcp.task_cancel import get_task_cancel

                get_task_cancel().clear()
                from hui_mcp.automation_consent import clear_automation_grant

                clear_automation_grant(task_id)
                return True
        return False

    def report_progress(self, task_id: str, step: str, message: str) -> bool:
        """Optional progress from Cursor side (stored for active task metadata)."""
        with self._lock:
            if not self._active or self._active.task_id != task_id:
                return False
            self._active.steps.append({"step": step, "message": message})
        return True


_relay = CursorRelay()


def get_relay() -> CursorRelay:
    return _relay
