"""User consent before Companion/Cursor drives mouse & keyboard."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable

from hui_mcp.context import AppContext

log = logging.getLogger("hui_mcp.automation_consent")

INPUT_AUTOMATION_TOOLS = frozenset(
    {
        "activate_document_app",
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_press",
        "keyboard_hotkey",
        "keyboard_type",
    }
)

NotifyFn = Callable[[dict[str, Any]], None]

_manager: AutomationConsentManager | None = None


def is_input_automation_tool(name: str) -> bool:
    return name in INPUT_AUTOMATION_TOOLS


def current_scope() -> str:
    from hui_mcp.active_task_store import read_active_task, read_active_voice
    from hui_mcp.cursor_relay import get_relay
    from hui_mcp.voice_relay import get_voice_relay

    voice = read_active_voice()
    if voice:
        return str(voice.get("utterance_id") or "").strip()
    pending_voice = get_voice_relay().get_pending()
    if pending_voice:
        uid = str(pending_voice.get("utterance_id") or "").strip()
        if uid:
            return uid
    task = read_active_task()
    if task:
        return str(task.get("task_id") or "").strip()
    pending = get_relay().get_pending()
    if pending:
        return str(pending.get("task_id") or "").strip()
    active = get_task_cancel_active_id()
    return active or "global"


def get_task_cancel_active_id() -> str | None:
    from hui_mcp.task_cancel import get_task_cancel

    return get_task_cancel().active_task_id()


class AutomationConsentManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._granted_scope: str | None = None
        self._notify: NotifyFn | None = None
        self._pending_id: str | None = None
        self._pending_event = threading.Event()
        self._pending_granted = False

    def set_companion_notify(self, fn: NotifyFn | None) -> None:
        self._notify = fn

    def clear_grant(self, scope: str | None = None) -> None:
        scope = (scope or "").strip()
        with self._lock:
            if not scope or self._granted_scope == scope:
                self._granted_scope = None

    def resolve(self, request_id: str, *, granted: bool) -> bool:
        request_id = (request_id or "").strip()
        with self._lock:
            if not self._pending_id or self._pending_id != request_id:
                return False
            self._pending_granted = granted
            self._pending_event.set()
        return True

    def ensure(self, ctx: AppContext, tool_name: str) -> dict[str, Any] | None:
        from hui_mcp.config import AppConfig

        cfg = AppConfig.load().automation
        ctx.config.automation = cfg
        if not cfg.require_consent:
            return None
        scope = current_scope()
        with self._lock:
            if self._granted_scope and self._granted_scope == scope:
                return None

        if not self._notify:
            return self._ensure_via_daemon(ctx, tool_name)

        request_id = uuid.uuid4().hex[:10]
        payload = {
            "type": "automation.consent.request",
            "request_id": request_id,
            "scope": scope,
            "tool": tool_name,
            "message": "Cursor 即将接管鼠标和键盘操作，是否允许？",
        }

        with self._lock:
            self._pending_id = request_id
            self._pending_granted = False
            self._pending_event.clear()

        try:
            self._notify(payload)
        except Exception as e:
            log.warning("automation consent notify failed: %s", e)
            return {
                "ok": False,
                "error": {
                    "code": "AUTOMATION_CONSENT_UNAVAILABLE",
                    "message": f"无法请求用户确认：{e}",
                },
            }

        timeout = max(5, int(cfg.consent_timeout_sec))
        if not self._pending_event.wait(timeout=timeout):
            with self._lock:
                if self._pending_id == request_id:
                    self._pending_id = None
            return {
                "ok": False,
                "error": {
                    "code": "AUTOMATION_CONSENT_TIMEOUT",
                    "message": "等待用户确认超时",
                },
            }

        with self._lock:
            granted = self._pending_granted
            if self._pending_id == request_id:
                self._pending_id = None
            if granted:
                self._granted_scope = scope
                return None

        return {
            "ok": False,
            "error": {
                "code": "AUTOMATION_DENIED",
                "message": "用户已取消任务",
            },
        }

    def _ensure_via_daemon(self, ctx: AppContext, tool_name: str) -> dict[str, Any] | None:
        """MCP stdio runs outside daemon; forward consent UI to Companion via daemon HTTP."""
        from hui_mcp.daemon_client import request_automation_consent

        timeout = max(10.0, float(ctx.config.automation.consent_timeout_sec) + 5.0)
        result = request_automation_consent(tool_name, timeout=timeout)
        if result.get("ok"):
            return None
        err = result.get("error")
        if isinstance(err, dict):
            return {"ok": False, "error": err}
        if isinstance(err, str):
            return {
                "ok": False,
                "error": {
                    "code": "AUTOMATION_CONSENT_UNAVAILABLE",
                    "message": err,
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "AUTOMATION_CONSENT_UNAVAILABLE",
                "message": "automation consent request failed",
            },
        }


def get_automation_consent() -> AutomationConsentManager:
    global _manager
    if _manager is None:
        _manager = AutomationConsentManager()
    return _manager


def ensure_automation_consent(ctx: AppContext, tool_name: str) -> dict[str, Any] | None:
    if not is_input_automation_tool(tool_name):
        return None
    return get_automation_consent().ensure(ctx, tool_name)


def clear_automation_grant(scope: str | None = None) -> None:
    get_automation_consent().clear_grant(scope)
