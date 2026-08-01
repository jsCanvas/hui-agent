"""Tests for doc_read status HTTP + disk persistence."""

from __future__ import annotations

import json
import socket
import threading
import time
from unittest.mock import patch

import pytest

from hui_mcp.agent.doc_read_store import get_doc_read_store, load_doc_read_snapshot
from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.daemon import _Handler, _Server
from hui_mcp.tools.handlers import handle_companion_doc_read_status


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def agent_http():
    cfg = AppConfig.load()
    ctx = AppContext(config=cfg)
    ctx.ensure_ring()
    runtime = AgentRuntime(ctx)
    _Handler.ctx = ctx
    _Handler.cfg = cfg
    _Handler.runtime = runtime
    port = _free_port()
    srv = _Server(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield port, ctx
    srv.shutdown()


def test_load_doc_read_snapshot_from_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("hui_mcp.agent.doc_read_store.DOC_READ_DIR", tmp_path)
    get_doc_read_store().clear("disk1")
    store = get_doc_read_store()
    store.start("disk1", "第四节")
    store.finish(
        "disk1",
        ocr_text="物流服务",
        ocr_preview="物流",
        edge_outline="要点",
        edge_model_used="builtin",
        pages=["/tmp/p1.png"],
    )
    with store._lock:
        store._jobs.pop("disk1", None)

    snap = load_doc_read_snapshot("disk1")
    assert snap is not None
    assert snap.status == "done"
    assert "物流" in snap.ocr_text
    assert snap.pages == ["/tmp/p1.png"]
    assert (tmp_path / "disk1.json").is_file()


def test_agent_doc_read_http(agent_http, tmp_path, monkeypatch):
    monkeypatch.setattr("hui_mcp.agent.doc_read_store.DOC_READ_DIR", tmp_path)
    port, _ctx = agent_http
    store = get_doc_read_store()
    store.start("t-doc", "第四节")
    store.append_progress("t-doc", "scroll", "第 1 屏")
    store.finish(
        "t-doc",
        ocr_text="买家端计费",
        ocr_preview="买家",
        edge_outline="3.2",
        edge_model_used="builtin",
        pages=["/tmp/a.png"],
    )

    import urllib.request

    url = f"http://127.0.0.1:{port}/agent/doc_read?task_id=t-doc"
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = json.loads(resp.read().decode())

    assert body["ok"] is True
    assert body["status"] == "done"
    assert "买家" in body["ocr_text"]
    assert body["pages"] == ["/tmp/a.png"]
    assert body["source"] == "daemon"
    store.clear("t-doc")


def test_handler_prefers_daemon(agent_http, tmp_path, monkeypatch):
    monkeypatch.setattr("hui_mcp.agent.doc_read_store.DOC_READ_DIR", tmp_path)
    port, ctx = agent_http
    store = get_doc_read_store()
    store.start("t-mcp", "第三节")
    store.finish(
        "t-mcp",
        ocr_text="第三节正文",
        ocr_preview="第三节",
        edge_outline="",
        pages=["/tmp/s.png"],
    )

    with patch("hui_mcp.daemon_client.BASE", f"http://127.0.0.1:{port}"):
        out = json.loads(handle_companion_doc_read_status(ctx, {"task_id": "t-mcp"}))

    assert out["ok"] is True
    assert out["status"] == "done"
    assert "第三节正文" in out["ocr_text"]
    store.clear("t-mcp")


def test_handler_falls_back_to_disk_when_daemon_down(tmp_path):
    cfg = AppConfig.load()
    ctx = AppContext(config=cfg)
    with patch("hui_mcp.agent.doc_read_store.DOC_READ_DIR", tmp_path):
        get_doc_read_store().clear("t-fallback")
        store = get_doc_read_store()
        store.start("t-fallback", "第四节")
        store.finish(
            "t-fallback",
            ocr_text="fallback ocr",
            ocr_preview="fallback",
            edge_outline="",
            pages=[],
        )
        with store._lock:
            store._jobs.pop("t-fallback", None)

        with patch(
            "hui_mcp.daemon_client._request",
            return_value={"ok": False, "error": "daemon unreachable"},
        ):
            out = json.loads(
                handle_companion_doc_read_status(ctx, {"task_id": "t-fallback"})
            )

    assert out["ok"] is True
    assert out["status"] == "done"
    assert "fallback ocr" in out["ocr_text"]
    assert out.get("source") == "disk"
    assert "daemon_unreachable" in out
    get_doc_read_store().clear("t-fallback")
