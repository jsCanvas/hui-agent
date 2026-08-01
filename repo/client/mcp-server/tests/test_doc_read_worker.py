"""Tests for background OCR document reader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.agent.doc_read_store import get_doc_read_store
from hui_mcp.agent.doc_read_worker import is_doc_read_task
from hui_mcp.agent.read_section_flow import _dedupe_pages


def test_is_doc_read_task_full():
    ok, section = is_doc_read_task("完整阅读物流服务文档第四节并总结")
    assert ok is True
    assert section == "第四节"


def test_is_doc_read_task_skip_coding():
    ok, _section = is_doc_read_task("帮我在项目里加一个登录按钮")
    assert ok is False


def test_dedupe_pages_by_hash():
    with patch("hui_mcp.agent.read_section_flow._content_hash") as mock_hash:
        mock_hash.side_effect = ["a", "a", "b"]
        pages = _dedupe_pages(["/p1.png", "/p2.png", "/p3.png"])
    assert pages == ["/p1.png", "/p3.png"]


def test_doc_read_store_lifecycle():
    store = get_doc_read_store()
    store.start("t1", "第四节")
    store.append_progress("t1", "scroll", "第 1 屏")
    store.finish(
        "t1",
        ocr_text="运费计算",
        ocr_preview="运费",
        edge_outline="要点",
        edge_model_used="builtin",
        pages=["/a.png"],
    )
    snap = store.get("t1")
    assert snap is not None
    assert snap.status == "done"
    assert snap.page_count == 1
    assert "运费" in snap.ocr_text
    store.clear("t1")
    assert store.get("t1") is None


def test_maybe_start_spawns_thread():
    from hui_mcp.agent.doc_read_worker import DocumentReadWorker

    worker = DocumentReadWorker()
    ctx = MagicMock()
    ctx.config.doc_read.enabled = True
    runtime = MagicMock()
    worker.set_deps(ctx, runtime)

    task = MagicMock()
    task.task_id = "t1"
    task.text = "完整阅读第四节并总结"

    with patch.object(worker, "_run"):
        started = worker.maybe_start(task)
    assert started is True
    store = get_doc_read_store()
    snap = store.get("t1")
    assert snap is not None
    assert snap.status == "running"
    store.clear("t1")
