"""Voice call session — STT → Agent → TTS loop."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from hui_mcp.agent.runtime import AgentResult, AgentRuntime
from hui_mcp.context import AppContext
from hui_mcp.tools.registry import invoke_tool
from hui_mcp.voice import player as audio_player
from hui_mcp.voice import stt as stt_engine
from hui_mcp.voice_relay import get_voice_relay

if TYPE_CHECKING:
    pass

log = logging.getLogger("hui_mcp.voice.call")

EventSink = Callable[[dict[str, Any]], None]
ProgressCallback = Callable[[str, str, str], None]

_session: VoiceCallSession | None = None


class VoiceCallSession:
    def __init__(self, ctx: AppContext, runtime: AgentRuntime) -> None:
        self.ctx = ctx
        self.runtime = runtime
        self.active = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.event_sink: EventSink | None = None

    def start(self, *, background_listen: bool | None = None) -> None:
        with self._lock:
            self.active = True
            self._stop.clear()
            use_bg = background_listen
            if use_bg is None:
                use_bg = self.ctx.config.stt.engine not in ("web", "")
            if use_bg and (self._thread is None or not self._thread.is_alive()):
                self._thread = threading.Thread(target=self._listen_loop, daemon=True)
                self._thread.start()
        get_voice_relay().start_session()
        from hui_mcp.active_task_store import clear_active_voice, read_active_voice

        if read_active_voice() and get_voice_relay().get_pending() is None:
            clear_active_voice()
        self._emit({"type": "voice.started"})

    def stop(self) -> None:
        with self._lock:
            self.active = False
            self._stop.set()
        audio_player.stop()
        get_voice_relay().stop_session()
        self._emit({"type": "voice.stopped"})

    def process_utterance(
        self,
        text: str,
        *,
        speak: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> AgentResult:
        text = (text or "").strip()
        if not text:
            return AgentResult(task_id="", ok=False, reply="未收到有效语音", steps=[])

        audio_player.stop()
        self._emit({"type": "voice.stt.final", "text": text, "confidence": 0.9})

        if self.ctx.config.effective_agent_mode() == "cursor" and self.active:
            if self.ctx.config.voice.enabled:
                from hui_mcp.voice.duplex_router import handle_voice_duplex

                outcome = handle_voice_duplex(self.ctx, text)
            else:
                outcome = get_voice_relay().submit_utterance(text)
            utterance_id = outcome.get("utterance_id") or ""
            ok = bool(outcome.get("ok"))
            reply = "" if ok else (outcome.get("error") or "语音 relay 失败")
            self._emit(
                {
                    "type": "voice.utterance.accepted",
                    "utterance_id": utterance_id,
                    "ok": ok,
                }
            )
            return AgentResult(
                task_id=utterance_id,
                ok=ok,
                reply=reply,
                steps=[{"step": "voice_relay", "message": "已通过 Socket 通知 Cursor"}],
            )

        def progress(task_id: str, step: str, message: str) -> None:
            self._emit(
                {
                    "type": "task.progress",
                    "task_id": task_id,
                    "step": step,
                    "message": message,
                }
            )
            if on_progress:
                on_progress(task_id, step, message)

        result = self.runtime.run(text, progress)
        self._emit(
            {
                "type": "chat.delta",
                "text": result.reply,
                "message_id": result.task_id,
                "ok": result.ok,
            }
        )
        if result.steps:
            self._emit(
                {
                    "type": "chat.steps",
                    "message_id": result.task_id,
                    "steps": [{"step": s.step, "message": s.message} for s in result.steps],
                }
            )
        self._emit({"type": "chat.done", "message_id": result.task_id, "ok": result.ok})

        if speak and result.reply:
            self._speak(result.reply)
        return result

    def stop_tts(self) -> None:
        audio_player.stop()
        self._emit({"type": "voice.tts.end"})

    def _speak(self, text: str) -> dict[str, Any]:
        self._emit({"type": "voice.tts.start", "text": text[:120]})
        out = invoke_tool(self.ctx, "tts_speak", {"text": text})
        self._emit({"type": "voice.tts.end"})
        return out

    def _listen_loop(self) -> None:
        while self.active and not self._stop.is_set():
            if self._stop.wait(0.2):
                break
            if audio_player.is_playing():
                continue
            result = stt_engine.listen_once(self.ctx.config.stt)
            if not self.active or self._stop.is_set():
                break
            if result.ok and result.text:
                self._emit(
                    {
                        "type": "voice.stt.final",
                        "text": result.text,
                        "confidence": result.confidence,
                    }
                )
                try:
                    self.process_utterance(result.text, speak=True)
                except Exception as e:
                    log.exception("voice utterance failed")
                    self._emit({"type": "error", "code": "VOICE_ERROR", "message": str(e)})
            elif result.error in ("TIMEOUT", "NO_SPEECH", "EMPTY"):
                continue
            elif result.error == "STT_WEB_ONLY":
                break
            else:
                log.warning("stt listen failed: %s", result.message or result.error)
                self._stop.wait(1.0)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink:
            try:
                self.event_sink(event)
            except Exception:
                log.exception("voice event sink failed")


def get_session(ctx: AppContext, runtime: AgentRuntime | None = None) -> VoiceCallSession:
    global _session
    if _session is None:
        _session = VoiceCallSession(ctx, runtime or AgentRuntime(ctx))
    return _session


def reset_session() -> None:
    global _session
    _session = None
