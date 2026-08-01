"""Voice call relay — multi-turn, non-blocking utterances over Socket."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

NotifyFn = Callable[[dict[str, Any]], None]


@dataclass
class VoiceTurn:
    utterance_id: str
    text: str
    created_at: float = field(default_factory=time.time)
    done: threading.Event = field(default_factory=threading.Event)
    ok: bool = False
    reply: str = ""
    duplex_plan: dict[str, Any] | None = None


class VoiceRelay:
    """Non-blocking voice turns: Companion STT → Cursor; Cursor speak → Companion."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._session_id = ""
        self._turns: dict[str, VoiceTurn] = {}
        self._order: list[str] = []
        self._notify_cursor: NotifyFn | None = None
        self._notify_companion: NotifyFn | None = None
        self._speak_lock = threading.Lock()
        self._pending_speak_done: dict[str, threading.Event] = {}

    def _estimate_speak_timeout(self, text: str) -> float:
        # ~8 chars/sec Chinese TTS + buffer; clamp for very long segments.
        return max(15.0, min(180.0, len(text) * 0.12 + 8.0))

    def _release_speak_waits(self) -> None:
        with self._speak_lock:
            for event in self._pending_speak_done.values():
                event.set()
            self._pending_speak_done.clear()

    def notify_speak_done(self, speak_id: str) -> bool:
        speak_id = (speak_id or "").strip()
        if not speak_id:
            return False
        with self._speak_lock:
            event = self._pending_speak_done.get(speak_id)
        if not event:
            return False
        event.set()
        return True

    def set_notify_cursor(self, fn: NotifyFn | None) -> None:
        self._notify_cursor = fn

    def set_notify_companion(self, fn: NotifyFn | None) -> None:
        self._notify_companion = fn

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start_session(self) -> str:
        with self._lock:
            self._active = True
            self._session_id = uuid.uuid4().hex[:12]
            self._turns.clear()
            self._order.clear()
            return self._session_id

    def stop_session(self) -> None:
        with self._lock:
            self._active = False
            for turn in self._turns.values():
                turn.ok = False
                turn.reply = ""
                turn.done.set()
            self._turns.clear()
            self._order.clear()
            self._session_id = ""

    def submit_utterance(
        self,
        text: str,
        *,
        duplex_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Accept user speech/text immediately; notify Cursor via Socket."""
        from hui_mcp.cursor_relay import get_relay

        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty text", "utterance_id": ""}

        if not get_relay().is_cursor_online():
            return {
                "ok": False,
                "error": "Cursor Socket 未连接，请运行 cursor-socket-client.py",
                "utterance_id": "",
            }

        utterance_id = uuid.uuid4().hex[:10]
        turn = VoiceTurn(
            utterance_id=utterance_id,
            text=text,
            duplex_plan=dict(duplex_plan) if duplex_plan else None,
        )
        with self._lock:
            if not self._active:
                self._active = True
                if not self._session_id:
                    self._session_id = uuid.uuid4().hex[:12]
            self._turns[utterance_id] = turn
            self._order.append(utterance_id)
            session_id = self._session_id

        payload: dict[str, Any] = {
            "type": "voice.user.message",
            "session_id": session_id,
            "utterance_id": utterance_id,
            "text": text,
        }
        if turn.duplex_plan:
            payload["duplex"] = turn.duplex_plan
        if self._notify_cursor:
            try:
                self._notify_cursor(payload)
            except Exception as e:
                with self._lock:
                    self._turns.pop(utterance_id, None)
                    if utterance_id in self._order:
                        self._order.remove(utterance_id)
                return {"ok": False, "error": str(e), "utterance_id": utterance_id}

        from hui_mcp.task_cancel import get_task_cancel

        get_task_cancel().begin(utterance_id)
        return {
            "ok": True,
            "utterance_id": utterance_id,
            "session_id": session_id,
            "duplex": turn.duplex_plan,
        }

    def begin_local_turn(
        self,
        text: str,
        *,
        duplex_plan: dict[str, Any] | None = None,
    ) -> str:
        """Edge-only turn without notifying Cursor."""
        text = (text or "").strip()
        utterance_id = uuid.uuid4().hex[:10]
        turn = VoiceTurn(
            utterance_id=utterance_id,
            text=text,
            duplex_plan=dict(duplex_plan) if duplex_plan else None,
        )
        with self._lock:
            if not self._active:
                self._active = True
                if not self._session_id:
                    self._session_id = uuid.uuid4().hex[:12]
            self._turns[utterance_id] = turn
            self._order.append(utterance_id)
        from hui_mcp.task_cancel import get_task_cancel

        get_task_cancel().begin(utterance_id)
        return utterance_id

    def update_duplex_plan(self, utterance_id: str, duplex_plan: dict[str, Any]) -> None:
        with self._lock:
            turn = self._turns.get(utterance_id)
            if turn:
                turn.duplex_plan = dict(duplex_plan)

    def relay_stt_partial(self, text: str, *, confidence: float | None = None) -> None:
        text = (text or "").strip()
        if not text or not self._notify_cursor:
            return
        payload: dict[str, Any] = {
            "type": "voice.stt.partial",
            "text": text,
            "session_id": self._session_id,
        }
        if confidence is not None:
            payload["confidence"] = confidence
        try:
            self._notify_cursor(payload)
        except Exception:
            pass

    def get_pending(self) -> dict[str, Any] | None:
        with self._lock:
            for uid in self._order:
                turn = self._turns.get(uid)
                if turn and not turn.done.is_set():
                    out: dict[str, Any] = {
                        "utterance_id": turn.utterance_id,
                        "text": turn.text,
                        "session_id": self._session_id,
                    }
                    if turn.duplex_plan:
                        out["duplex"] = turn.duplex_plan
                    return out
            return None

    def speak(
        self,
        text: str,
        *,
        utterance_id: str | None = None,
        final: bool = False,
        interrupt: bool = False,
        wait_playback: bool = True,
    ) -> dict[str, Any]:
        """Push TTS text to Companion over Socket (Cursor → Companion)."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "text required"}

        if interrupt:
            self._release_speak_waits()

        speak_id = uuid.uuid4().hex[:10]
        payload: dict[str, Any] = {
            "type": "voice.speak",
            "text": text,
            "final": bool(final),
            "interrupt": bool(interrupt),
            "speak_id": speak_id,
        }
        if utterance_id:
            payload["utterance_id"] = utterance_id
        if self._session_id:
            payload["session_id"] = self._session_id

        if not self._notify_companion:
            return {"ok": False, "error": "companion socket offline"}

        done_event = threading.Event()
        with self._speak_lock:
            self._pending_speak_done[speak_id] = done_event

        try:
            self._notify_companion(payload)
        except Exception as e:
            with self._speak_lock:
                self._pending_speak_done.pop(speak_id, None)
            return {"ok": False, "error": str(e)}

        if wait_playback:
            timeout = self._estimate_speak_timeout(text)
            if not done_event.wait(timeout=timeout):
                with self._speak_lock:
                    self._pending_speak_done.pop(speak_id, None)
                return {
                    "ok": True,
                    "text": text[:120],
                    "final": bool(final),
                    "speak_id": speak_id,
                    "playback_done": False,
                    "warning": "playback timeout",
                }

        with self._speak_lock:
            self._pending_speak_done.pop(speak_id, None)
        return {
            "ok": True,
            "text": text[:120],
            "final": bool(final),
            "speak_id": speak_id,
            "playback_done": True,
        }

    def complete_turn(
        self,
        utterance_id: str,
        *,
        reply: str,
        ok: bool = True,
    ) -> bool:
        with self._lock:
            turn = self._turns.get(utterance_id)
            if not turn or turn.done.is_set():
                return False
            turn.ok = ok
            turn.reply = reply
            turn.done.set()

        if self._notify_companion:
            try:
                self._notify_companion(
                    {
                        "type": "voice.turn.done",
                        "utterance_id": utterance_id,
                        "ok": ok,
                        "reply": reply,
                        "session_id": self._session_id,
                    }
                )
            except Exception:
                pass

        from hui_mcp.task_cancel import get_task_cancel
        from hui_mcp.automation_consent import clear_automation_grant

        ctrl = get_task_cancel()
        if ctrl.active_task_id() == utterance_id:
            ctrl.clear()
        clear_automation_grant(utterance_id)
        return True

    def has_active_turn(self, utterance_id: str) -> bool:
        utterance_id = (utterance_id or "").strip()
        if not utterance_id:
            return False
        with self._lock:
            turn = self._turns.get(utterance_id)
            return bool(turn and not turn.done.is_set())

    def cancel_turn(self, utterance_id: str, *, reason: str = "用户终止") -> bool:
        """Cancel a voice utterance: stop TTS, notify Companion, clear pending files."""
        from hui_mcp.active_task_store import clear_task_artifacts

        utterance_id = (utterance_id or "").strip()
        if not utterance_id:
            return False

        active = self.has_active_turn(utterance_id)
        self.speak(
            "好的，已终止当前任务。",
            utterance_id=utterance_id,
            interrupt=True,
            final=True,
        )
        if active:
            self.complete_turn(utterance_id, reply=reason, ok=False)
        elif self._notify_companion:
            try:
                self._notify_companion(
                    {
                        "type": "voice.turn.done",
                        "utterance_id": utterance_id,
                        "ok": False,
                        "reply": reason,
                        "session_id": self._session_id,
                    }
                )
            except Exception:
                pass
        clear_task_artifacts(utterance_id)
        from hui_mcp.task_cancel import get_task_cancel

        ctrl = get_task_cancel()
        if ctrl.active_task_id() == utterance_id:
            ctrl.clear()
        return True

    def wait_turn(
        self,
        utterance_id: str,
        *,
        timeout_sec: float = 600,
    ) -> dict[str, Any] | None:
        with self._lock:
            turn = self._turns.get(utterance_id)
        if not turn:
            return None
        if not turn.done.wait(timeout=timeout_sec):
            return None
        return {"ok": turn.ok, "reply": turn.reply, "utterance_id": utterance_id}


_voice_relay = VoiceRelay()


def get_voice_relay() -> VoiceRelay:
    return _voice_relay
