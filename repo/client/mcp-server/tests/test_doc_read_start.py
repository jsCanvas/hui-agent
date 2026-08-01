"""Tests for doc read start HTTP + MCP handler."""

from __future__ import annotations

import json
import socket
import threading
import time
from unittest.mock import patch

import pytest

from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.daemon import _Handler, _Server
from hui_mcp.tools.handlers import handle_companion_doc_read_start


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
    from hui_mcp.cursor_relay import get_relay

    get_relay().set_worker_deps(ctx, runtime)
    port = _free_port()
    srv = _Server(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield port, ctx
    srv.shutdown()


def test_companion_doc_read_start_proxies_daemon():
    ctx = AppContext(config=AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.get_pending",
        return_value={"ok": True, "pending": {"task_id": "t1", "text": "完整阅读第四节并总结"}},
    ), patch(
        "hui_mcp.daemon_client.start_doc_read",
        return_value={"ok": True, "task_id": "t1", "section": "第四节"},
    ) as mock_start:
        out = handle_companion_doc_read_start(ctx, {})
    mock_start.assert_called_once_with("t1", text="完整阅读第四节并总结")
    data = json.loads(out)
    assert data["ok"] is True
    assert data["section"] == "第四节"


def test_agent_doc_read_start_http(agent_http, monkeypatch):
    from hui_mcp.agent.doc_read_store import get_doc_read_store
    from hui_mcp.cursor_relay import RelayTask, get_relay

    port, _ctx = agent_http
    monkeypatch.setattr(
        "hui_mcp.agent.doc_read_worker.DocumentReadWorker.maybe_start",
        lambda self, task, _cb: True,
    )
    relay = get_relay()
    task = RelayTask(task_id="t-start", text="完整阅读第四节并总结")
    relay._active = task

    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/agent/doc_read/start",
        data=json.dumps({"task_id": "t-start"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read().decode())
    assert body["ok"] is True
    assert body["section"] == "第四节"
    get_doc_read_store().clear("t-start")
