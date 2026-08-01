"""Daemon agent/chat HTTP tests."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import HTTPServer
from unittest.mock import patch

import pytest

from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.daemon import _Handler, _Server


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


@patch("hui_mcp.agent.runtime.invoke_tool")
def test_agent_chat_http(mock_invoke, agent_http):
    def fake_tool(ctx, name, arguments=None):
        return {
            "get_screenshot": {"ok": True, "result": {"path": "/tmp/s.png"}},
            "keyboard_hotkey": {"ok": True, "result": {"ok": True}},
            "keyboard_type": {"ok": True, "result": {"ok": True}},
            "keyboard_press": {"ok": True, "result": {"ok": True}},
            "get_recent_frames": {"ok": True, "result": {"directory": "/tmp/f"}},
        }.get(name, {"ok": True, "result": {}})

    mock_invoke.side_effect = fake_tool

    port, ctx = agent_http
    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/agent/chat",
        data=json.dumps({"text": "阅读需求文档第三节"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    assert body["ok"] is True
    assert "第三节" in body["reply"]
    assert len(body["steps"]) >= 2
    ctx.ring.stop() if ctx.ring else None


def test_agent_complete_http(agent_http):
    from hui_mcp.cursor_relay import get_relay

    port, ctx = agent_http
    relay = get_relay()
    task = __import__("hui_mcp.cursor_relay", fromlist=["RelayTask"]).RelayTask(
        task_id="t1",
        text="test",
    )
    relay._active = task  # noqa: SLF001

    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/agent/complete",
        data=json.dumps({"task_id": "t1", "reply": "summary"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read().decode())
    assert body["ok"] is True
    assert task.done.is_set()
    ctx.ring.stop() if ctx.ring else None
