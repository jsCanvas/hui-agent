"""TCP Socket Bridge — NDJSON protocol for real-time Agent interaction."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.cursor_relay import get_relay
from hui_mcp.tools.registry import invoke_tool, list_tool_names
from hui_mcp.voice.call_session import get_session
from hui_mcp.voice_relay import get_voice_relay

log = logging.getLogger("hui_mcp.socket")
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[socket] %(message)s")

INPUT_TOOL_PREFIXES = ("mouse_", "keyboard_", "tts_")


@dataclass
class ClientSession:
    bridge: SocketBridge
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    authenticated: bool = False
    frame_fps: float = 0.0
    frame_task: asyncio.Task | None = None
    closed: bool = False
    role: str = "client"

    async def send(self, payload: dict[str, Any]) -> None:
        if self.closed:
            return
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.writer.write(line.encode("utf-8"))
        await self.writer.drain()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.frame_task and not self.frame_task.done():
            self.frame_task.cancel()
            try:
                await self.frame_task
            except asyncio.CancelledError:
                pass
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
        self.bridge.remove_client(self)


class SocketBridge:
    def __init__(self, ctx: AppContext, cfg: AppConfig) -> None:
        self.ctx = ctx
        self.cfg = cfg
        self.host = cfg.socket.host
        self.port = cfg.socket.port
        self.token = cfg.socket.token
        self._tool_lock = asyncio.Lock()
        self._clients: list[ClientSession] = []
        self._server: asyncio.Server | None = None
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cursor_session: ClientSession | None = None
        self._companion_session: ClientSession | None = None
        self._cursor_auto: bool = False
        relay = get_relay()
        relay.set_notify(self._notify_cursor_task)
        voice = get_voice_relay()
        voice.set_notify_cursor(self._notify_cursor_voice)
        voice.set_notify_companion(self._notify_companion)
        from hui_mcp.automation_consent import get_automation_consent

        get_automation_consent().set_companion_notify(self._notify_companion)

    @property
    def running(self) -> bool:
        return self._server is not None

    def remove_client(self, session: ClientSession) -> None:
        if session in self._clients:
            self._clients.remove(session)
        if session is self._cursor_session:
            self._cursor_session = None
            get_relay().set_cursor_online(False)
        if session is self._companion_session:
            self._companion_session = None

    def _notify_cursor_task(self, task) -> None:
        session = self._cursor_session
        loop = self._loop
        if not session or loop is None:
            raise RuntimeError("cursor socket session offline")
        from hui_mcp.agent.doc_read_worker import is_doc_read_task

        is_doc, _ = is_doc_read_task(task.text)
        payload = {
            "type": "task.request",
            "task_id": task.task_id,
            "text": task.text,
            "doc_read": is_doc,
            "no_focus": is_doc,
            "cursor_background": False,
        }
        asyncio.run_coroutine_threadsafe(session.send(payload), loop)
        self._notify_companion_agent_started(
            task_id=task.task_id,
            text=task.text,
            channel="text",
        )

    def _notify_companion_agent_started(
        self,
        *,
        task_id: str,
        text: str,
        channel: str,
    ) -> None:
        from hui_mcp.notify import macos_notify

        preview = (text or "").strip().replace("\n", " ")[:80]
        if channel == "voice":
            macos_notify("Companion", "Cursor 已开始处理语音任务", preview or task_id[:8])
        else:
            macos_notify("Companion", "Cursor 已开始处理任务", preview or task_id[:8])
        try:
            self._notify_companion(
                {
                    "type": "agent.task.started",
                    "task_id": task_id,
                    "text": (text or "")[:120],
                    "channel": channel,
                }
            )
        except RuntimeError:
            log.debug("companion offline, skip agent.task.started UI sync")

    def _notify_cursor_voice(self, payload: dict[str, Any]) -> None:
        session = self._cursor_session
        loop = self._loop
        if not session or loop is None:
            raise RuntimeError("Cursor Socket 未连接，请运行 companion_socket_connect")
        asyncio.run_coroutine_threadsafe(session.send(payload), loop)
        if payload.get("type") == "voice.user.message":
            self._notify_companion_agent_started(
                task_id=str(payload.get("utterance_id") or ""),
                text=str(payload.get("text") or ""),
                channel="voice",
            )

    def _notify_companion(self, payload: dict[str, Any]) -> None:
        session = self._companion_session
        loop = self._loop
        if not session or loop is None:
            raise RuntimeError("companion socket offline")
        asyncio.run_coroutine_threadsafe(session.send(payload), loop)

    def notify_companion_event(self, payload: dict[str, Any]) -> None:
        """Push a UI event to Companion (best-effort)."""
        try:
            self._notify_companion(payload)
        except RuntimeError:
            log.debug("companion offline, skip event %s", payload.get("type"))

    def companion_online(self) -> bool:
        return self._companion_session is not None and not self._companion_session.closed

    async def start(self) -> None:
        if self._server is not None:
            return
        self._loop = asyncio.get_running_loop()
        try:
            self._server = await asyncio.start_server(
                self._handle_connection,
                self.host,
                self.port,
            )
            log.info("listening on %s:%s", self.host, self.port)
        except OSError as e:
            if getattr(e, "errno", None) != 48:
                raise
            log.warning(
                "socket port %s:%s already in use — reuse existing bridge",
                self.host,
                self.port,
            )
        self._ready.set()

    async def stop(self) -> None:
        if self._server is None:
            return
        for session in list(self._clients):
            await session.close()
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        log.info("stopped")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        session = ClientSession(bridge=self, reader=reader, writer=writer)
        self._clients.append(session)
        peer = writer.get_extra_info("peername")
        log.info("client connected %s session=%s", peer, session.session_id)
        try:
            while not session.closed:
                line = await reader.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    await session.send(
                        {
                            "type": "error",
                            "code": "INVALID_JSON",
                            "message": "expected NDJSON object",
                        }
                    )
                    continue
                await self._dispatch(session, msg)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            await session.close()
            log.info("client disconnected session=%s", session.session_id)

    async def _dispatch(self, session: ClientSession, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "auth":
            await self._handle_auth(session, msg)
            return
        if not session.authenticated:
            await session.send(
                {
                    "type": "error",
                    "code": "UNAUTHORIZED",
                    "message": "send auth first",
                }
            )
            return

        if mtype == "ping":
            await session.send({"type": "pong"})
        elif mtype == "tool.invoke":
            await self._handle_tool_invoke(session, msg)
        elif mtype == "frame.subscribe":
            await self._handle_frame_subscribe(session, msg)
        elif mtype == "frame.unsubscribe":
            await self._handle_frame_unsubscribe(session)
        elif mtype == "chat.send":
            await self._handle_chat_send(session, msg)
        elif mtype == "agent.register":
            await self._handle_agent_register(session, msg)
        elif mtype == "task.progress":
            await self._handle_task_progress(msg)
        elif mtype == "task.result":
            await self._handle_task_result(msg)
        elif mtype == "voice.start":
            await self._handle_voice_start(session, msg)
        elif mtype == "voice.stop":
            await self._handle_voice_stop(session)
        elif mtype == "voice.stt.partial":
            await self._handle_voice_stt_partial(session, msg)
        elif mtype == "voice.stt.final":
            await self._handle_voice_stt_final(session, msg)
        elif mtype == "voice.speak":
            await self._handle_voice_speak_from_cursor(session, msg)
        elif mtype == "voice.speak.done":
            await self._handle_voice_speak_done(session, msg)
        elif mtype == "voice.turn.complete":
            await self._handle_voice_turn_complete(msg)
        elif mtype == "automation.consent.response":
            await self._handle_automation_consent(session, msg)
        elif mtype == "tools.list":
            await session.send({"type": "tools.list", "tools": list_tool_names()})
        else:
            await session.send(
                {
                    "type": "error",
                    "code": "UNKNOWN_TYPE",
                    "message": f"unsupported type: {mtype}",
                }
            )

    async def _handle_auth(self, session: ClientSession, msg: dict[str, Any]) -> None:
        token = msg.get("token", "")
        if token != self.token:
            await session.send(
                {
                    "type": "auth.fail",
                    "code": "INVALID_TOKEN",
                    "message": "token mismatch",
                }
            )
            await session.close()
            return
        session.authenticated = True
        await session.send({"type": "auth.ok", "session_id": session.session_id})

    async def _handle_agent_register(self, session: ClientSession, msg: dict[str, Any]) -> None:
        role = (msg.get("role") or "client").lower()
        session.role = role
        if role == "cursor":
            if self._cursor_session and self._cursor_session is not session:
                await session.send(
                    {
                        "type": "error",
                        "code": "CURSOR_BUSY",
                        "message": "another cursor session already registered",
                    }
                )
                return
            self._cursor_session = session
            self._cursor_auto = bool(msg.get("auto", False))
            get_relay().set_cursor_online(True)
            log.info(
                "cursor agent registered session=%s auto=%s",
                session.session_id,
                self._cursor_auto,
            )
        elif role == "companion":
            if self._companion_session and self._companion_session is not session:
                await session.send(
                    {
                        "type": "error",
                        "code": "COMPANION_BUSY",
                        "message": "another companion session already registered",
                    }
                )
                return
            self._companion_session = session
            log.info("companion registered session=%s", session.session_id)
        await session.send(
            {
                "type": "agent.registered",
                "role": role,
                "auto": self._cursor_auto if role == "cursor" else False,
            }
        )

    async def _handle_task_progress(self, msg: dict[str, Any]) -> None:
        task_id = msg.get("task_id") or ""
        step = msg.get("step") or "progress"
        message = msg.get("message") or ""
        if task_id:
            get_relay().report_progress(task_id, step, message)

    async def _handle_task_result(self, msg: dict[str, Any]) -> None:
        task_id = msg.get("task_id") or ""
        if not task_id:
            return
        steps = msg.get("steps")
        if steps is not None and not isinstance(steps, list):
            steps = None
        get_relay().complete_task(
            task_id,
            reply=msg.get("reply") or "",
            ok=bool(msg.get("ok", True)),
            steps=steps,
            data=msg.get("data") if isinstance(msg.get("data"), dict) else None,
        )

    async def _handle_tool_invoke(self, session: ClientSession, msg: dict[str, Any]) -> None:
        req_id = msg.get("id") or uuid.uuid4().hex
        name = msg.get("name")
        arguments = msg.get("arguments") or {}
        if not name:
            await session.send(
                {
                    "type": "tool.result",
                    "id": req_id,
                    "ok": False,
                    "error": {"code": "VALIDATION_ERROR", "message": "name required"},
                }
            )
            return

        needs_lock = name.startswith(INPUT_TOOL_PREFIXES)
        try:
            if needs_lock:
                async with self._tool_lock:
                    outcome = await asyncio.to_thread(invoke_tool, self.ctx, name, arguments)
            else:
                outcome = await asyncio.to_thread(invoke_tool, self.ctx, name, arguments)
        except Exception as e:
            outcome = {"ok": False, "error": {"code": "TOOL_ERROR", "message": str(e)}}

        payload: dict[str, Any] = {"type": "tool.result", "id": req_id, "ok": outcome["ok"]}
        if outcome["ok"]:
            payload["result"] = outcome.get("result")
        else:
            payload["error"] = outcome.get("error")
        await session.send(payload)

    async def _handle_frame_subscribe(self, session: ClientSession, msg: dict[str, Any]) -> None:
        fps = float(msg.get("fps") or 2)
        fps = max(0.5, min(fps, 10.0))
        await self._handle_frame_unsubscribe(session)
        session.frame_fps = fps
        session.frame_task = asyncio.create_task(self._frame_push_loop(session))
        await session.send({"type": "frame.subscribed", "fps": fps})

    async def _handle_frame_unsubscribe(self, session: ClientSession) -> None:
        if session.frame_task and not session.frame_task.done():
            session.frame_task.cancel()
            try:
                await session.frame_task
            except asyncio.CancelledError:
                pass
        session.frame_task = None
        session.frame_fps = 0.0

    async def _frame_push_loop(self, session: ClientSession) -> None:
        interval = 1.0 / session.frame_fps
        while session.frame_fps > 0 and not session.closed:
            slot = await asyncio.to_thread(self._latest_frame_path)
            if slot:
                path, ts, index = slot
                await session.send(
                    {
                        "type": "frame.push",
                        "path": path,
                        "timestamp_ms": ts,
                        "index": index,
                    }
                )
            await asyncio.sleep(interval)

    def _latest_frame_path(self) -> tuple[str, int, int] | None:
        ring = self.ctx.ensure_ring()
        slot = ring.latest_slot()
        if slot is None:
            return None
        return str(slot.filepath), slot.timestamp_ms, slot.index

    async def _handle_chat_send(self, session: ClientSession, msg: dict[str, Any]) -> None:
        text = (msg.get("text") or "").strip()
        if not text:
            await session.send(
                {
                    "type": "error",
                    "code": "VALIDATION_ERROR",
                    "message": "text required",
                }
            )
            return

        loop = asyncio.get_running_loop()

        if self.ctx.config.effective_agent_mode() == "cursor":
            relay = get_relay()

            def on_progress(task_id: str, step: str, message: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    session.send(
                        {
                            "type": "task.progress",
                            "task_id": task_id,
                            "step": step,
                            "message": message,
                        }
                    ),
                    loop,
                )

            outcome = await asyncio.to_thread(relay.run_task, text, on_progress)
            message_id = outcome["task_id"]
            await session.send(
                {
                    "type": "chat.delta",
                    "text": outcome["reply"],
                    "message_id": message_id,
                    "ok": outcome["ok"],
                }
            )
            steps = outcome.get("steps") or []
            if steps:
                await session.send(
                    {
                        "type": "chat.steps",
                        "message_id": message_id,
                        "steps": steps,
                    }
                )
            await session.send({"type": "chat.done", "message_id": message_id, "ok": outcome["ok"]})
            return

        runtime = AgentRuntime(self.ctx)

        def on_progress(task_id: str, step: str, message: str) -> None:
            asyncio.run_coroutine_threadsafe(
                session.send(
                    {
                        "type": "task.progress",
                        "task_id": task_id,
                        "step": step,
                        "message": message,
                    }
                ),
                loop,
            )

        result = await asyncio.to_thread(runtime.run, text, on_progress)
        message_id = result.task_id
        await session.send(
            {
                "type": "chat.delta",
                "text": result.reply,
                "message_id": message_id,
                "ok": result.ok,
            }
        )
        if result.steps:
            await session.send(
                {
                    "type": "chat.steps",
                    "message_id": message_id,
                    "steps": [{"step": s.step, "message": s.message} for s in result.steps],
                }
            )
        await session.send({"type": "chat.done", "message_id": message_id, "ok": result.ok})

    async def _handle_voice_start(self, session: ClientSession, msg: dict[str, Any]) -> None:
        runtime = AgentRuntime(self.ctx)
        voice = get_session(self.ctx, runtime)
        bg = msg.get("background_listen")
        loop = asyncio.get_running_loop()

        def sink(event: dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(session.send(event), loop)

        voice.event_sink = sink
        await asyncio.to_thread(
            voice.start,
            background_listen=bg if isinstance(bg, bool) else None,
        )

    async def _handle_voice_stop(self, session: ClientSession) -> None:
        runtime = AgentRuntime(self.ctx)
        voice = get_session(self.ctx, runtime)
        await asyncio.to_thread(voice.stop)
        await asyncio.to_thread(get_voice_relay().stop_session)

    async def _handle_voice_stt_partial(self, session: ClientSession, msg: dict[str, Any]) -> None:
        if session.role != "companion":
            await session.send(
                {
                    "type": "error",
                    "code": "FORBIDDEN",
                    "message": "voice.stt.partial requires companion role",
                }
            )
            return
        text = (msg.get("text") or "").strip()
        if not text:
            return
        conf = msg.get("confidence")
        confidence = float(conf) if isinstance(conf, (int, float)) else None
        await asyncio.to_thread(get_voice_relay().relay_stt_partial, text, confidence=confidence)
        await session.send({"type": "voice.stt.ack", "partial": True, "text": text[:80]})

    async def _handle_voice_stt_final(self, session: ClientSession, msg: dict[str, Any]) -> None:
        if session.role != "companion":
            await session.send(
                {
                    "type": "error",
                    "code": "FORBIDDEN",
                    "message": "voice.stt.final requires companion role",
                }
            )
            return
        text = (msg.get("text") or "").strip()
        if not text:
            await session.send(
                {
                    "type": "error",
                    "code": "VALIDATION_ERROR",
                    "message": "text required",
                }
            )
            return
        if self.ctx.config.voice.enabled:
            from hui_mcp.voice.duplex_router import handle_voice_duplex

            outcome = await asyncio.to_thread(handle_voice_duplex, self.ctx, text)
        else:
            outcome = await asyncio.to_thread(get_voice_relay().submit_utterance, text)
        await session.send(
            {
                "type": "voice.utterance.accepted",
                "ok": outcome.get("ok", False),
                "utterance_id": outcome.get("utterance_id", ""),
                "session_id": outcome.get("session_id", ""),
                "error": outcome.get("error"),
                "edge_only": outcome.get("edge_only", False),
                "duplex": outcome.get("duplex"),
            }
        )

    async def _handle_voice_speak_from_cursor(self, session: ClientSession, msg: dict[str, Any]) -> None:
        if session.role != "cursor":
            await session.send(
                {
                    "type": "error",
                    "code": "FORBIDDEN",
                    "message": "voice.speak from cursor session only via MCP companion_speak",
                }
            )
            return
        text = (msg.get("text") or "").strip()
        if not text:
            return
        utterance_id = msg.get("utterance_id")
        uid = utterance_id if isinstance(utterance_id, str) else None
        outcome = await asyncio.to_thread(
            get_voice_relay().speak,
            text,
            utterance_id=uid,
            final=bool(msg.get("final", False)),
            interrupt=bool(msg.get("interrupt", False)),
        )
        await session.send({"type": "voice.speak.ack", "ok": outcome.get("ok", False), **outcome})

    async def _handle_voice_speak_done(self, session: ClientSession, msg: dict[str, Any]) -> None:
        if session.role != "companion":
            await session.send(
                {
                    "type": "error",
                    "code": "FORBIDDEN",
                    "message": "voice.speak.done requires companion role",
                }
            )
            return
        speak_id = (msg.get("speak_id") or "").strip()
        if not speak_id:
            return
        ok = await asyncio.to_thread(get_voice_relay().notify_speak_done, speak_id)
        await session.send({"type": "voice.speak.done.ack", "ok": ok, "speak_id": speak_id})

    async def _handle_automation_consent(
        self, session: ClientSession, msg: dict[str, Any]
    ) -> None:
        if session.role != "companion":
            await session.send(
                {
                    "type": "error",
                    "code": "FORBIDDEN",
                    "message": "automation.consent.response requires companion role",
                }
            )
            return
        request_id = (msg.get("request_id") or "").strip()
        granted = bool(msg.get("granted"))
        from hui_mcp.automation_consent import get_automation_consent

        ok = get_automation_consent().resolve(request_id, granted=granted)
        if not ok:
            await session.send(
                {
                    "type": "automation.consent.ack",
                    "ok": False,
                    "error": "unknown or expired request_id",
                }
            )
            return
        if not granted:
            from hui_mcp.task_cancel import cancel_active

            await asyncio.to_thread(
                cancel_active,
                reason="用户拒绝鼠标键盘自动化",
            )
        await session.send(
            {
                "type": "automation.consent.ack",
                "ok": True,
                "granted": granted,
                "request_id": request_id,
            }
        )

    async def _handle_voice_turn_complete(self, msg: dict[str, Any]) -> None:
        utterance_id = (msg.get("utterance_id") or msg.get("task_id") or "").strip()
        reply = (msg.get("reply") or "").strip()
        if not utterance_id:
            return
        await asyncio.to_thread(
            get_voice_relay().complete_turn,
            utterance_id,
            reply=reply,
            ok=bool(msg.get("ok", True)),
        )


_bridge: SocketBridge | None = None
_bridge_thread: threading.Thread | None = None


def _run_loop(bridge: SocketBridge) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _main() -> None:
        bridge._loop = asyncio.get_running_loop()
        await bridge.start()
        try:
            await loop.create_future()
        except asyncio.CancelledError:
            pass
        finally:
            await bridge.stop()

    try:
        loop.run_until_complete(_main())
    finally:
        loop.close()


def start_bridge_thread(ctx: AppContext, cfg: AppConfig) -> SocketBridge:
    global _bridge, _bridge_thread
    if _bridge is not None and _bridge.running:
        return _bridge
    _bridge = SocketBridge(ctx, cfg)
    _bridge_thread = threading.Thread(
        target=_run_loop,
        args=(_bridge,),
        daemon=True,
        name="socket-bridge",
    )
    _bridge_thread.start()
    if not _bridge._ready.wait(timeout=5):
        raise RuntimeError("socket bridge failed to start within 5s")
    return _bridge


def get_bridge() -> SocketBridge | None:
    return _bridge


def main() -> None:
    from hui_mcp.voice import manager as voice_manager

    cfg = AppConfig.load()
    if cfg.tts.auto_start_proxy:
        voice_manager.ensure_proxy(cfg)
    ctx = AppContext(config=cfg)
    ctx.ensure_ring()

    async def _run() -> None:
        bridge = SocketBridge(ctx, cfg)
        await bridge.start()
        log.info("auth token prefix: %s...", cfg.socket.token[:8])
        try:
            await asyncio.Event().wait()
        finally:
            await bridge.stop()
            ctx.ring.stop() if ctx.ring else None

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        ctx.ring.stop() if ctx.ring else None


if __name__ == "__main__":
    main()
