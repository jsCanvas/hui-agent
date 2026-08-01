"""Daemon voice HTTP tests."""

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
from hui_mcp.voice.call_session import reset_session


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def voice_http():
    reset_session()
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
    reset_session()


@patch("hui_mcp.voice.call_session.invoke_tool")
@patch("hui_mcp.agent.runtime.invoke_tool")
def test_voice_utterance_http(mock_runtime_tool, mock_voice_tool, voice_http):
    mock_runtime_tool.return_value = {"ok": True, "result": {}}
    mock_voice_tool.return_value = {"ok": True, "result": {"duration_ms": 50}}

    port, ctx = voice_http
    import urllib.request

    urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{port}/voice/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=5,
    )

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/voice/utterance",
        data=json.dumps({"text": "帮助", "speak": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    assert body["ok"] is True
    assert "向下滚动" in body["reply"]
    ctx.ring.stop() if ctx.ring else None
