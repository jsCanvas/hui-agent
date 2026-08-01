"""Shared doc-read status response for Daemon HTTP and MCP handlers."""

from __future__ import annotations

from typing import Any, Callable

from hui_mcp.agent.doc_read_store import DocReadSnapshot, load_doc_read_snapshot
from hui_mcp.context import AppContext
from hui_mcp.ocr.extract import ocr_available


def resolve_doc_read_task_id(
    task_id: str | None,
    *,
    get_pending_fn: Callable[[], dict] | None = None,
) -> str | None:
    tid = (task_id or "").strip()
    if tid:
        return tid
    if get_pending_fn is None:
        from hui_mcp.daemon_client import get_pending

        get_pending_fn = get_pending
    pending = get_pending_fn()
    if pending.get("ok") and pending.get("pending"):
        resolved = (pending["pending"].get("task_id") or "").strip()
        if resolved:
            return resolved
    return None


def build_doc_read_status_response(
    ctx: AppContext,
    snap: DocReadSnapshot | None,
    *,
    task_id: str,
    include_full_ocr: bool = True,
    source: str | None = None,
) -> dict[str, Any]:
    if snap is None:
        return {
            "ok": True,
            "task_id": task_id,
            "status": "pending",
            "message": "后台 OCR 尚未开始或任务非文档阅读",
            "source": source or "none",
        }

    body = snap.to_dict(include_full_ocr=include_full_ocr)
    body["ok"] = True
    body["source"] = source or "store"
    body["ocr_available"] = ocr_available()
    from hui_mcp.agent.edge_model import edge_outline_status

    body["edge"] = edge_outline_status(ctx.config)
    if snap.edge_model_used:
        body["edge_model_used"] = snap.edge_model_used
    body["reading_policy"] = {
        "edge_outline_role": "辅助索引，不可替代 Cursor 完整阅读",
        "cursor_must": [
            "阅读完整 ocr_text",
            "逐张查看 pages 截图（Read 工具读图）并对照浏览器",
            "流程图/UI 截图以视觉理解为准",
            "禁止仅依据 edge_outline 写摘要",
        ],
    }
    return body


def fetch_doc_read_status(
    ctx: AppContext,
    task_id: str,
    *,
    include_full_ocr: bool = True,
) -> dict[str, Any]:
    """Load status from Daemon memory/disk snapshot."""
    snap = load_doc_read_snapshot(task_id)
    return build_doc_read_status_response(
        ctx,
        snap,
        task_id=task_id,
        include_full_ocr=include_full_ocr,
        source="daemon" if snap else "none",
    )
