"""Background OCR document reader — dual-path with Cursor (non-blocking)."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from hui_mcp.agent.doc_read_store import get_doc_read_store
from hui_mcp.agent.intents import IntentKind, classify
from hui_mcp.agent.read_section_flow import build_summary, scroll_capture_pages, search_section
from hui_mcp.ocr.extract import ocr_available
from hui_mcp.task_cancel import TaskCancelled, get_task_cancel

if TYPE_CHECKING:
    from hui_mcp.agent.runtime import AgentRuntime
    from hui_mcp.context import AppContext
    from hui_mcp.cursor_relay import RelayTask

log = logging.getLogger("hui_mcp.doc_read")

ProgressFn = Callable[[str, str], None]
RelayProgressFn = Callable[[str, str, str], None]

INPUT_TOOLS = frozenset(
    {
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_press",
        "keyboard_hotkey",
        "keyboard_type",
    }
)


def is_doc_read_task(text: str) -> tuple[bool, str | None]:
    t = text.strip()
    if re.search(r"\.(?:md|markdown|txt)", t, re.I) and any(
        k in t for k in ("阅读", "读", "总结", "归纳", "全文")
    ):
        return True, None

    intent = classify(text)
    if intent.kind == IntentKind.READ_DOC_SECTION_FULL:
        return True, intent.section_query
    if intent.kind == IntentKind.READ_DOC_SECTION:
        keys = ("完整", "总结", "归纳", "全文", "阅读", "读", "章节", "文档", "飞书")
        if any(k in text for k in keys):
            return True, intent.section_query
    return False, None


def _edge_outline(app_cfg, section: str, ocr_text: str) -> tuple[str, str]:
    doc = app_cfg.doc_read
    if not doc.edge_outline:
        return "", "none"
    if len(ocr_text.strip()) < 40:
        return "", "none"
    try:
        from hui_mcp.agent.edge_model import build_outline

        return build_outline(section, ocr_text, app_cfg)
    except Exception as e:
        log.warning("edge outline failed: %s", e)
        from hui_mcp.agent.edge_model import build_local_outline

        return build_local_outline(section, ocr_text), "builtin"


class DocumentReadWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._ctx: AppContext | None = None
        self._runtime: AgentRuntime | None = None

    def set_deps(self, ctx: AppContext, runtime: AgentRuntime) -> None:
        self._ctx = ctx
        self._runtime = runtime

    def maybe_start(
        self,
        task: RelayTask,
        on_relay_progress: RelayProgressFn | None = None,
    ) -> bool:
        ctx = self._ctx
        runtime = self._runtime
        if ctx is None or runtime is None:
            return False
        if not ctx.config.doc_read.enabled:
            get_doc_read_store().skip(task.task_id, "doc_read disabled")
            return False

        ok, section = is_doc_read_task(task.text)
        if not ok or not section:
            get_doc_read_store().skip(task.task_id, "not a document read task")
            return False

        store = get_doc_read_store()
        store.start(task.task_id, section)

        def relay_progress(step: str, message: str) -> None:
            store.append_progress(task.task_id, step, message)
            if on_relay_progress:
                on_relay_progress(task.task_id, step, message)

        with self._lock:
            if self._thread and self._thread.is_alive():
                log.info("doc read worker busy, queue skipped for %s", task.task_id)
                store.skip(task.task_id, "worker busy")
                return False
            self._thread = threading.Thread(
                target=self._run,
                args=(task.task_id, section, ctx, runtime, relay_progress),
                name=f"doc-read-{task.task_id}",
                daemon=True,
            )
            self._thread.start()
        return True

    def _tool(self, runtime: AgentRuntime, name: str, arguments: dict | None = None) -> dict:
        from hui_mcp.tools.registry import invoke_tool

        ctx = runtime.ctx
        if name in INPUT_TOOLS:
            key = (arguments or {}).get("key", "")
            if str(key).lower() in ("esc", "escape") and get_task_cancel().is_active():
                get_task_cancel().suppress_esc_cancel()
            with runtime._lock:
                return invoke_tool(ctx, name, arguments or {})
        return invoke_tool(ctx, name, arguments or {})

    def _run(
        self,
        task_id: str,
        section_query: str,
        ctx: AppContext,
        runtime: AgentRuntime,
        progress: ProgressFn,
    ) -> None:
        store = get_doc_read_store()
        cfg = ctx.config.doc_read
        tool = lambda name, args=None: self._tool(runtime, name, args)
        cancel = get_task_cancel()
        cancel_check = cancel.is_cancelled

        try:
            keep_fg = cfg.assume_doc_foreground
            progress("doc_read", f"后台 OCR 阅读「{section_query}」…")
            progress("doc_read", "按 Esc 可立即终止任务")
            if keep_fg:
                progress("doc_read", "保持当前前台页面，不切换窗口")
            else:
                from hui_mcp.input.focus import activate_browser_for_reading

                activate_browser_for_reading()
                time.sleep(0.15)
            if not ocr_available():
                progress("doc_read", "未安装 tesseract，仍将滚屏采集截图")

            if cancel_check():
                raise TaskCancelled()

            ok, err = search_section(
                tool, section_query, progress, keep_foreground=keep_fg, cancel_check=cancel_check
            )
            if not ok:
                if cancel_check():
                    raise TaskCancelled()
                store.finish(
                    task_id,
                    ocr_text="",
                    ocr_preview="",
                    edge_outline="",
                    pages=[],
                    ok=False,
                    error=err or "search failed",
                )
                progress("error", err or "搜索章节失败")
                return

            pages = scroll_capture_pages(
                tool,
                progress,
                section_query=section_query,
                max_pages=cfg.max_pages,
                page_downs=cfg.page_downs,
                scroll_dy=cfg.scroll_dy,
                stale_hits_to_stop=cfg.stale_hits_to_stop,
                keep_foreground=keep_fg,
                cancel_check=cancel_check,
            )
            if cancel_check():
                raise TaskCancelled()
            if not pages:
                shot = tool("get_screenshot", {})
                from hui_mcp.agent.read_section_flow import _result_path

                p = _result_path(shot)
                if p:
                    pages = [p]

            progress("ocr", f"OCR 识别 {len(pages)} 屏…")
            _summary, full_ocr, _snippets = build_summary(section_query, pages)
            preview = full_ocr[: cfg.ocr_preview_chars]
            if len(full_ocr) > cfg.ocr_preview_chars:
                preview += "\n\n…（完整 OCR 见 companion_doc_read_status）"

            progress("outline", "本地边缘模型整理大纲…")
            outline, edge_used = _edge_outline(ctx.config, section_query, full_ocr)

            store.finish(
                task_id,
                ocr_text=full_ocr,
                ocr_preview=preview,
                edge_outline=outline,
                edge_model_used=edge_used,
                pages=pages,
                ok=True,
            )
            progress(
                "done",
                f"OCR 完成：{len(pages)} 屏，{len(full_ocr)} 字"
                + (f"，大纲 {len(outline)} 字（{edge_used}）" if outline else ""),
            )
            if cfg.notify_on_complete:
                from hui_mcp.notify import macos_notify

                macos_notify(
                    "Companion OCR 完成",
                    task_id[:8],
                    f"{len(pages)} 屏 / {len(full_ocr)} 字，等待 Cursor 写摘要",
                )
        except TaskCancelled:
            snap = store.get(task_id)
            if snap and snap.status == "running":
                store.finish(
                    task_id,
                    ocr_text="",
                    ocr_preview="",
                    edge_outline="",
                    pages=[],
                    ok=False,
                    error="用户按 Esc 终止",
                )
                progress("cancel", "用户按 Esc 终止")
        except Exception as e:
            log.exception("doc read worker failed")
            if cfg.notify_on_complete:
                from hui_mcp.notify import macos_notify

                macos_notify("Companion OCR 失败", task_id[:8], str(e)[:80])
            store.finish(
                task_id,
                ocr_text="",
                ocr_preview="",
                edge_outline="",
                pages=[],
                ok=False,
                error=str(e),
            )
            progress("error", str(e))


_worker = DocumentReadWorker()


def get_doc_read_worker() -> DocumentReadWorker:
    return _worker
