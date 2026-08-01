"""Socket Bridge integration tests."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest

from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.cursor_relay import get_relay
from hui_mcp.socket_bridge import SocketBridge


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def bridge_ctx():
    cfg = AppConfig.load()
    cfg.socket.port = _free_port()
    cfg.socket.token = "test-token-12345"
    cfg.agent.mode = "rules"
    ctx = AppContext(config=cfg)
    ctx.ensure_ring()
    # warm ring
    time.sleep(0.2)
    bridge = SocketBridge(ctx, cfg)
    thread = threading.Thread(
        target=lambda: asyncio.run(_serve(bridge)),
        daemon=True,
    )
    thread.start()
    assert bridge._ready.wait(timeout=5)
    yield bridge, cfg, ctx
    asyncio.run(bridge.stop())
    ctx.ring.stop() if ctx.ring else None


async def _serve(bridge: SocketBridge) -> None:
    await bridge.start()
    try:
        while bridge.running:
            await asyncio.sleep(0.2)
    finally:
        await bridge.stop()


async def _exchange(host: str, port: int, messages: list[dict]) -> list[dict]:
    reader, writer = await asyncio.open_connection(host, port)
    out: list[dict] = []
    for msg in messages:
        writer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=5)
        out.append(json.loads(line.decode()))
    writer.close()
    await writer.wait_closed()
    return out


def test_auth_and_ping(bridge_ctx):
    bridge, cfg, _ctx = bridge_ctx

    async def run():
        replies = await _exchange(
            cfg.socket.host,
            cfg.socket.port,
            [
                {"type": "auth", "token": cfg.socket.token},
                {"type": "ping"},
            ],
        )
        assert replies[0]["type"] == "auth.ok"
        assert replies[1]["type"] == "pong"

    asyncio.run(run())


def test_auth_fail(bridge_ctx):
    bridge, cfg, _ctx = bridge_ctx

    async def run():
        reader, writer = await asyncio.open_connection(cfg.socket.host, cfg.socket.port)
        writer.write(b'{"type":"auth","token":"wrong"}\n')
        await writer.drain()
        line = await reader.readline()
        data = json.loads(line.decode())
        assert data["type"] == "auth.fail"
        writer.close()
        await writer.wait_closed()

    asyncio.run(run())


def test_tool_invoke_get_screen_info(bridge_ctx):
    bridge, cfg, _ctx = bridge_ctx

    async def run():
        replies = await _exchange(
            cfg.socket.host,
            cfg.socket.port,
            [
                {"type": "auth", "token": cfg.socket.token},
                {
                    "type": "tool.invoke",
                    "id": "t1",
                    "name": "get_screen_info",
                    "arguments": {},
                },
            ],
        )
        result = replies[1]
        assert result["type"] == "tool.result"
        assert result["ok"] is True
        assert "width" in result["result"]

    asyncio.run(run())


def test_unauthorized_before_auth(bridge_ctx):
    bridge, cfg, _ctx = bridge_ctx

    async def run():
        replies = await _exchange(
            cfg.socket.host,
            cfg.socket.port,
            [{"type": "ping"}],
        )
        assert replies[0]["type"] == "error"
        assert replies[0]["code"] == "UNAUTHORIZED"

    asyncio.run(run())


async def _chat_until_done(host: str, port: int, token: str, text: str) -> list[dict]:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write((json.dumps({"type": "auth", "token": token}) + "\n").encode())
    await writer.drain()
    await reader.readline()
    writer.write((json.dumps({"type": "chat.send", "text": text}) + "\n").encode())
    await writer.drain()
    msgs: list[dict] = []
    while True:
        line = await asyncio.wait_for(reader.readline(), timeout=10)
        msgs.append(json.loads(line.decode()))
        if msgs[-1].get("type") == "chat.done":
            break
    writer.close()
    await writer.wait_closed()
    return msgs


def test_chat_send_help(bridge_ctx):
    _bridge, cfg, _ctx = bridge_ctx

    async def run():
        msgs = await _chat_until_done(cfg.socket.host, cfg.socket.port, cfg.socket.token, "帮助")
        types = [m["type"] for m in msgs]
        assert "chat.delta" in types
        assert msgs[-1]["type"] == "chat.done"
        assert msgs[-1]["ok"] is True
        delta = next(m for m in msgs if m["type"] == "chat.delta")
        assert "向下滚动" in delta["text"]

    asyncio.run(run())


def test_cursor_register_and_relay_chat(bridge_ctx):
    _bridge, cfg, _ctx = bridge_ctx
    cfg.agent.mode = "cursor"
    relay = get_relay()
    relay.set_cursor_online(False)

    async def run():
        reader, writer = await asyncio.open_connection(cfg.socket.host, cfg.socket.port)
        writer.write((json.dumps({"type": "auth", "token": cfg.socket.token}) + "\n").encode())
        await writer.drain()
        assert json.loads((await reader.readline()).decode())["type"] == "auth.ok"

        writer.write((json.dumps({"type": "agent.register", "role": "cursor"}) + "\n").encode())
        await writer.drain()
        assert json.loads((await reader.readline()).decode())["type"] == "agent.registered"
        assert relay.is_cursor_online() is True

        chat_task = asyncio.create_task(
            _chat_until_done(cfg.socket.host, cfg.socket.port, cfg.socket.token, "帮助")
        )
        await asyncio.sleep(0.05)
        pending = relay.get_pending()
        assert pending is not None
        relay.complete_task(pending["task_id"], reply="relay ok", ok=True)

        msgs = await asyncio.wait_for(chat_task, timeout=5)
        delta = next(m for m in msgs if m["type"] == "chat.delta")
        assert delta["text"] == "relay ok"
        assert msgs[-1]["ok"] is True

        writer.close()
        await writer.wait_closed()

    asyncio.run(run())
    relay.set_cursor_online(False)


def test_companion_voice_stt_relay(bridge_ctx):
    _bridge, cfg, _ctx = bridge_ctx
    from hui_mcp.voice_relay import get_voice_relay

    voice = get_voice_relay()
    voice.stop_session()
    voice.start_session()
    cursor_msgs: list[dict] = []
    voice.set_notify_cursor(lambda p: cursor_msgs.append(p))

    async def run():
        reader, writer = await asyncio.open_connection(cfg.socket.host, cfg.socket.port)
        writer.write((json.dumps({"type": "auth", "token": cfg.socket.token}) + "\n").encode())
        await writer.drain()
        await reader.readline()

        writer.write((json.dumps({"type": "agent.register", "role": "cursor"}) + "\n").encode())
        await writer.drain()
        await reader.readline()

        comp_reader, comp_writer = await asyncio.open_connection(cfg.socket.host, cfg.socket.port)
        comp_writer.write((json.dumps({"type": "auth", "token": cfg.socket.token}) + "\n").encode())
        await comp_writer.drain()
        await comp_reader.readline()
        comp_writer.write(
            (json.dumps({"type": "agent.register", "role": "companion"}) + "\n").encode()
        )
        await comp_writer.drain()
        await comp_reader.readline()

        comp_writer.write(
            (json.dumps({"type": "voice.stt.final", "text": "帮我总结文档"}) + "\n").encode()
        )
        await comp_writer.drain()
        ack_line = await asyncio.wait_for(comp_reader.readline(), timeout=3)
        ack = json.loads(ack_line.decode())
        assert ack["type"] == "voice.utterance.accepted"
        assert ack["ok"] is True

        await asyncio.sleep(0.05)
        assert any(m.get("type") == "voice.user.message" for m in cursor_msgs)

        comp_writer.close()
        await comp_writer.wait_closed()
        writer.close()
        await writer.wait_closed()

    asyncio.run(run())
    voice.stop_session()
