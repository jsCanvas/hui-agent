"""Background daemon: capture ring + health HTTP + Socket Bridge + Agent Runtime."""

from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

from hui_mcp.active_task_store import (
    clear_task_artifacts,
    read_active_task,
    read_active_voice,
)
from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.cursor_relay import get_relay
from hui_mcp.socket_bridge import get_bridge, start_bridge_thread
from hui_mcp.voice.call_session import get_session
from hui_mcp.voice_relay import get_voice_relay

log = logging.getLogger("hui_mcp.daemon")
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[daemon] %(message)s")

DAEMON_PORT = int(__import__("os").environ.get("HUI_AGENT_DAEMON_PORT", "18766"))


class _Handler(BaseHTTPRequestHandler):
    ctx: AppContext
    cfg: AppConfig
    runtime: AgentRuntime

    def log_message(self, fmt: str, *args) -> None:
        log.debug(fmt, *args)

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            ring = self.ctx.ensure_ring()
            slots = ring.snapshot()
            bridge = get_bridge()
            from hui_mcp.cursor_socket_manager import read_watch_metadata

            watch = read_watch_metadata()
            body = {
                "ok": True,
                "frames_buffered": len(slots),
                "fps": ring.fps,
                "socket": {
                    "host": self.cfg.socket.host,
                    "port": self.cfg.socket.port,
                    "running": bridge.running if bridge else False,
                },
                "agent": {
                    "ready": True,
                    "mode": self.cfg.effective_agent_mode(),
                    "cursor_online": get_relay().is_cursor_online(),
                    "companion_online": bridge.companion_online() if bridge else False,
                    "cursor_waiting": bool(watch.get("cursor_waiting")),
                    "cursor_wait_since": watch.get("cursor_wait_since"),
                    "watch_running": bool(watch.get("running")),
                    "watch_remaining_sec": watch.get("remaining_sec"),
                },
                "voice": {
                    "active": get_session(self.ctx, self.runtime).active,
                    "relay_active": get_voice_relay().is_active(),
                },
            }
            self._send_json(200, body)
            return
        if path == "/agent/pending":
            pending = get_relay().get_pending()
            if pending is None:
                pending = read_active_task()
            voice_pending = get_voice_relay().get_pending()
            if voice_pending is None:
                voice_pending = read_active_voice()
            if pending and voice_pending:
                voice_id = (voice_pending.get("utterance_id") or "").strip()
                if voice_id and pending.get("task_id") == voice_id:
                    pending = None
            self._send_json(
                200,
                {
                    "ok": True,
                    "pending": pending,
                    "voice_pending": voice_pending,
                    "cursor_online": get_relay().is_cursor_online(),
                },
            )
            return
        if path == "/agent/doc_read":
            qs = parse_qs(parsed.query)
            task_id = (qs.get("task_id") or [""])[0].strip()
            full_raw = (qs.get("full_ocr") or ["1"])[0].lower()
            include_full = full_raw not in ("0", "false", "no")
            if not task_id:
                pending = get_relay().get_pending() or read_active_task()
                if pending:
                    task_id = (pending.get("task_id") or "").strip()
            if not task_id:
                self._send_json(400, {"ok": False, "error": "task_id required or no pending task"})
                return
            from hui_mcp.agent.doc_read_status import fetch_doc_read_status

            body = fetch_doc_read_status(
                self.ctx,
                task_id,
                include_full_ocr=include_full,
            )
            self._send_json(200, body)
            return
        if path == "/voice/stt/poll":
            from hui_mcp.voice.stt_session import get_stt_session

            self._send_json(200, get_stt_session().poll())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/agent/cancel":
            try:
                body = self._read_json_body()
                task_id = (body.get("task_id") or "").strip()
                reason = (body.get("reason") or "用户终止").strip() or "用户终止"
                from hui_mcp.task_cancel import cancel_active, cancel_task

                if task_id:
                    result = cancel_task(task_id, reason=reason)
                else:
                    result = cancel_active(reason=reason)
                code = 200 if result.get("ok") else 404
                self._send_json(code, result)
            except Exception as e:
                log.exception("agent/cancel failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/agent/wait/notify":
            try:
                body = self._read_json_body()
                waiting = bool(body.get("waiting"))
                from hui_mcp.cursor_socket_manager import read_watch_metadata

                watch = read_watch_metadata()
                bridge = get_bridge()
                if bridge and bridge.companion_online():
                    try:
                        bridge.notify_companion_event(
                            {
                                "type": "agent.wait.state",
                                "waiting": waiting,
                                "remaining_sec": watch.get("remaining_sec"),
                            }
                        )
                    except RuntimeError:
                        pass
                self._send_json(200, {"ok": True, "waiting": waiting})
            except Exception as e:
                log.exception("agent/wait/notify failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/automation/consent/request":
            try:
                body = self._read_json_body()
                tool = (body.get("tool") or "").strip()
                if not tool:
                    self._send_json(
                        400,
                        {
                            "ok": False,
                            "error": {
                                "code": "INVALID",
                                "message": "tool required",
                            },
                        },
                    )
                    return
                from hui_mcp.automation_consent import ensure_automation_consent

                blocked = ensure_automation_consent(self.ctx, tool)
                if blocked is None:
                    self._send_json(200, {"ok": True, "granted": True})
                    return
                self._send_json(200, blocked)
            except Exception as e:
                log.exception("automation/consent/request failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/agent/complete":
            try:
                body = self._read_json_body()
                task_id = (body.get("task_id") or body.get("utterance_id") or "").strip()
                reply = (body.get("reply") or "").strip()
                if not task_id or not reply:
                    self._send_json(400, {"ok": False, "error": "task_id and reply required"})
                    return
                if get_voice_relay().complete_turn(
                    task_id,
                    reply=reply,
                    ok=bool(body.get("ok", True)),
                ):
                    clear_task_artifacts(task_id)
                    self._send_json(200, {"ok": True, "task_id": task_id, "channel": "voice"})
                    return
                stale_voice = read_active_voice()
                if stale_voice and stale_voice.get("utterance_id") == task_id:
                    clear_task_artifacts(task_id)
                    self._send_json(
                        200,
                        {"ok": True, "task_id": task_id, "channel": "voice", "cleared_stale": True},
                    )
                    return
                ok = get_relay().complete_task(
                    task_id,
                    reply=reply,
                    ok=bool(body.get("ok", True)),
                )
                if not ok:
                    self._send_json(404, {"ok": False, "error": "no matching active task"})
                    return
                clear_task_artifacts(task_id)
                self._send_json(200, {"ok": True, "task_id": task_id, "channel": "text"})
            except Exception as e:
                log.exception("agent/complete failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/agent/doc_read/start":
            try:
                body = self._read_json_body()
                task_id = (body.get("task_id") or "").strip()
                pending = get_relay().get_pending() or read_active_task()
                if not task_id and pending:
                    task_id = (pending.get("task_id") or "").strip()
                text = (body.get("text") or "").strip()
                if not text and pending:
                    text = (pending.get("text") or "").strip()
                if not task_id or not text:
                    self._send_json(400, {"ok": False, "error": "task_id and text required"})
                    return
                from hui_mcp.agent.doc_read_worker import get_doc_read_worker, is_doc_read_task
                from hui_mcp.cursor_relay import RelayTask

                ok, section = is_doc_read_task(text)
                if not ok or not section:
                    self._send_json(400, {"ok": False, "error": "not a document read task"})
                    return
                task = RelayTask(task_id=task_id, text=text)
                started = get_doc_read_worker().maybe_start(task, None)
                self._send_json(
                    200,
                    {
                        "ok": started,
                        "task_id": task_id,
                        "section": section,
                        "message": "OCR worker started" if started else "worker busy or skipped",
                    },
                )
            except Exception as e:
                log.exception("agent/doc_read/start failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/agent/chat":
            try:
                body = self._read_json_body()
                text = (body.get("text") or "").strip()
                if not text:
                    self._send_json(400, {"ok": False, "error": "text required"})
                    return
                result = self.runtime.run(text)
                self._send_json(200, result.to_dict())
            except Exception as e:
                log.exception("agent/chat failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/start":
            try:
                body = self._read_json_body()
                bg = body.get("background_listen")
                session = get_session(self.ctx, self.runtime)
                session.start(background_listen=bg if isinstance(bg, bool) else None)
                self._send_json(200, {"ok": True, "active": True})
            except Exception as e:
                log.exception("voice/start failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/stop":
            try:
                get_session(self.ctx, self.runtime).stop()
                self._send_json(200, {"ok": True, "active": False})
            except Exception as e:
                log.exception("voice/stop failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/utterance":
            try:
                body = self._read_json_body()
                text = (body.get("text") or "").strip()
                speak = body.get("speak", True)
                if not text:
                    self._send_json(400, {"ok": False, "error": "text required"})
                    return
                session = get_session(self.ctx, self.runtime)
                result = session.process_utterance(text, speak=bool(speak))
                self._send_json(200, result.to_dict())
            except Exception as e:
                log.exception("voice/utterance failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/speak":
            try:
                body = self._read_json_body()
                text = (body.get("text") or "").strip()
                if not text:
                    self._send_json(400, {"ok": False, "error": "text required"})
                    return
                utterance_id = body.get("utterance_id")
                uid = utterance_id if isinstance(utterance_id, str) else None
                result = get_voice_relay().speak(
                    text,
                    utterance_id=uid,
                    final=bool(body.get("final", False)),
                    interrupt=bool(body.get("interrupt", False)),
                )
                code = 200 if result.get("ok") else 503
                self._send_json(code, result)
            except Exception as e:
                log.exception("voice/speak failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/turn/complete":
            try:
                body = self._read_json_body()
                utterance_id = (body.get("utterance_id") or "").strip()
                reply = (body.get("reply") or "").strip()
                if not utterance_id or not reply:
                    self._send_json(400, {"ok": False, "error": "utterance_id and reply required"})
                    return
                ok = get_voice_relay().complete_turn(
                    utterance_id,
                    reply=reply,
                    ok=bool(body.get("ok", True)),
                )
                if not ok:
                    stale = read_active_voice()
                    if stale and stale.get("utterance_id") == utterance_id:
                        clear_task_artifacts(utterance_id)
                        self._send_json(
                            200,
                            {"ok": True, "utterance_id": utterance_id, "cleared_stale": True},
                        )
                        return
                    self._send_json(404, {"ok": False, "error": "no matching voice turn"})
                    return
                clear_task_artifacts(utterance_id)
                self._send_json(200, {"ok": True, "utterance_id": utterance_id})
            except Exception as e:
                log.exception("voice/turn/complete failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/stt/start":
            try:
                from hui_mcp.voice.stt_session import get_stt_session

                body = self._read_json_body()
                language = (body.get("language") or self.ctx.config.stt.language or "zh-CN").strip()
                continuous = bool(body.get("continuous", False))
                result = get_stt_session().start(language=language, continuous=continuous)
                self._send_json(200, result)
            except Exception as e:
                log.exception("voice/stt/start failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/stt/stop":
            try:
                from hui_mcp.voice.stt_session import get_stt_session

                self._send_json(200, get_stt_session().stop())
            except Exception as e:
                log.exception("voice/stt/stop failed")
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/voice/tts/stop":
            try:
                get_session(self.ctx, self.runtime).stop_tts()
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        self.send_error(404)


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _daemon_already_running() -> bool:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{DAEMON_PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def main() -> None:
    if _daemon_already_running():
        log.info("daemon already running on :%s, skip duplicate start", DAEMON_PORT)
        return

    cfg = AppConfig.load()
    ctx = AppContext(config=cfg)
    ctx.ensure_ring()
    runtime = AgentRuntime(ctx)
    log.info("capture ring started (%sfps)", ctx.ring.fps if ctx.ring else 10)

    bridge = start_bridge_thread(ctx, cfg)
    get_relay().set_worker_deps(ctx, runtime)
    if cfg.doc_read.esc_cancel_enabled:
        from hui_mcp.input.esc_listener import start_esc_listener

        start_esc_listener()
    log.info(
        "socket bridge %s:%s (token prefix %s...)",
        cfg.socket.host,
        cfg.socket.port,
        cfg.socket.token[:8],
    )

    _Handler.ctx = ctx
    _Handler.cfg = cfg
    _Handler.runtime = runtime
    srv = _Server(("127.0.0.1", DAEMON_PORT), _Handler)
    log.info("health http://127.0.0.1:%s/health", DAEMON_PORT)
    log.info("agent chat POST http://127.0.0.1:%s/agent/chat", DAEMON_PORT)
    log.info("agent cancel POST http://127.0.0.1:%s/agent/cancel", DAEMON_PORT)
    log.info(
        "automation consent POST http://127.0.0.1:%s/automation/consent/request",
        DAEMON_PORT,
    )
    log.info("doc read GET http://127.0.0.1:%s/agent/doc_read?task_id=", DAEMON_PORT)
    log.info("doc read POST http://127.0.0.1:%s/agent/doc_read/start", DAEMON_PORT)
    log.info("voice call POST http://127.0.0.1:%s/voice/{start,stop,utterance}", DAEMON_PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        ctx.ring.stop() if ctx.ring else None


if __name__ == "__main__":
    main()
