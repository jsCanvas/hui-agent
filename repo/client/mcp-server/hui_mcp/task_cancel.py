"""Global task cancellation (Esc hotkey + HTTP cancel)."""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("hui_mcp.task_cancel")


class TaskCancelled(Exception):
    """Raised when OCR / relay work should stop immediately."""


class TaskCancelController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._task_id: str | None = None
        self._suppress_until = 0.0
        self._last_cancel_at = 0.0

    def begin(self, task_id: str) -> None:
        with self._lock:
            self._task_id = task_id
            self._event.clear()

    def clear(self) -> None:
        with self._lock:
            self._task_id = None
            self._event.clear()

    def active_task_id(self) -> str | None:
        with self._lock:
            return self._task_id

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._task_id)

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def suppress_esc_cancel(self, seconds: float = 0.45) -> None:
        with self._lock:
            self._suppress_until = time.time() + max(0.05, seconds)

    def _esc_allowed(self) -> bool:
        with self._lock:
            if not self._task_id:
                return False
            return time.time() >= self._suppress_until

    def signal(self, *, reason: str = "用户按 Esc 终止") -> dict:
        with self._lock:
            now = time.time()
            if now - self._last_cancel_at < 0.35:
                return {"ok": True, "debounced": True}
            self._last_cancel_at = now
            task_id = self._task_id
            self._event.set()
        if not task_id:
            return {"ok": False, "error": "no active task"}
        return cancel_task(task_id, reason=reason)

    def check(self) -> None:
        if self._event.is_set():
            raise TaskCancelled()


_controller = TaskCancelController()


def get_task_cancel() -> TaskCancelController:
    return _controller


def _resolve_voice_utterance_id(task_id: str = "") -> str:
    from hui_mcp.active_task_store import read_active_voice
    from hui_mcp.voice_relay import get_voice_relay

    task_id = (task_id or "").strip()
    relay = get_voice_relay()
    if task_id and relay.has_active_turn(task_id):
        return task_id
    pending = relay.get_pending()
    if pending:
        uid = (pending.get("utterance_id") or "").strip()
        if uid and (not task_id or uid == task_id):
            return uid
    voice = read_active_voice()
    if voice:
        uid = (voice.get("utterance_id") or "").strip()
        if uid and (not task_id or uid == task_id):
            return uid
    return task_id if task_id and relay.has_active_turn(task_id) else ""


def cancel_task(task_id: str, *, reason: str = "用户终止") -> dict:
    """Cancel OCR worker, text relay, or voice utterance."""
    from hui_mcp.active_task_store import clear_active_task, read_active_task
    from hui_mcp.agent.doc_read_store import get_doc_read_store, load_doc_read_snapshot
    from hui_mcp.cursor_relay import get_relay
    from hui_mcp.notify import macos_notify
    from hui_mcp.voice_relay import get_voice_relay

    task_id = (task_id or "").strip()
    voice_id = _resolve_voice_utterance_id(task_id)
    if voice_id:
        get_task_cancel()._event.set()
        get_voice_relay().cancel_turn(voice_id, reason=reason)
        get_task_cancel().clear()
        macos_notify("Companion 通话已终止", voice_id[:8], reason)
        log.info("voice turn cancelled: %s (%s)", voice_id, reason)
        return {
            "ok": True,
            "task_id": voice_id,
            "utterance_id": voice_id,
            "cancelled": True,
            "reason": reason,
            "channel": "voice",
        }

    if not task_id:
        return {"ok": False, "error": "task_id required"}

    get_task_cancel()._event.set()

    snap = load_doc_read_snapshot(task_id)
    store = get_doc_read_store()
    if snap and snap.status in ("running", "pending"):
        store.finish(
            task_id,
            ocr_text="",
            ocr_preview="",
            edge_outline="",
            pages=[],
            ok=False,
            error=reason,
        )
        store.append_progress(task_id, "cancel", reason)

    relay = get_relay()
    completed = relay.complete_task(task_id, reply=reason, ok=False)
    if not completed:
        stale = read_active_task()
        if stale and stale.get("task_id") == task_id:
            relay.complete_task(task_id, reply=reason, ok=False)

    clear_active_task()
    get_task_cancel().clear()

    macos_notify("Companion 任务已终止", task_id[:8], reason)
    log.info("task cancelled: %s (%s)", task_id, reason)
    return {"ok": True, "task_id": task_id, "cancelled": True, "reason": reason}


def cancel_active(*, reason: str = "用户按 Esc 终止") -> dict:
    task_id = get_task_cancel().active_task_id()
    if task_id:
        return cancel_task(task_id, reason=reason)

    voice_id = _resolve_voice_utterance_id()
    if voice_id:
        return cancel_task(voice_id, reason=reason)

    from hui_mcp.active_task_store import read_active_task
    from hui_mcp.cursor_relay import get_relay

    pending = get_relay().get_pending() or read_active_task()
    task_id = (pending or {}).get("task_id") or ""
    if not task_id:
        return {"ok": False, "error": "no active task"}
    return cancel_task(task_id, reason=reason)


def on_esc_pressed() -> None:
    ctrl = get_task_cancel()
    if not ctrl._esc_allowed():
        return
    try:
        ctrl.signal(reason="用户按 Esc 终止")
    except Exception:
        log.exception("esc cancel failed")
