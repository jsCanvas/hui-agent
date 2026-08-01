"""MCP companion handlers proxy to daemon HTTP."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.context import AppContext
from hui_mcp.tools.handlers import (
    handle_companion_connection_status,
    handle_companion_speak,
    handle_companion_task_complete,
    handle_companion_task_pending,
)


def test_companion_task_pending_proxies_daemon():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.get_pending",
        return_value={"ok": True, "pending": {"task_id": "abc", "text": "hello"}},
    ):
        out = handle_companion_task_pending(ctx, {})
    assert '"task_id": "abc"' in out


def test_companion_speak_proxies_daemon():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.voice_speak",
        return_value={"ok": True, "text": "你好"},
    ) as mock_speak:
        out = handle_companion_speak(ctx, {"text": "你好", "final": True})
    mock_speak.assert_called_once()
    assert '"ok": true' in out.lower()


def test_companion_task_complete_proxies_daemon():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.complete_task",
        return_value={"ok": True, "task_id": "abc"},
    ) as mock_complete, patch(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        return_value={
            "ok": True,
            "running": True,
            "remaining_sec": 3600,
            "cursor_online": True,
        },
    ), patch(
        "hui_mcp.tools.handlers.handle_companion_socket_wait",
        return_value='{"ok": true, "continue_waiting": true, "agent_next": "companion_socket_wait"}',
    ) as mock_wait:
        out = handle_companion_task_complete(
            ctx,
            {"task_id": "abc", "reply": "done"},
        )
    mock_complete.assert_called_once_with("abc", "done", ok=True)
    mock_wait.assert_called_once()
    assert '"ok": true' in out.lower()
    assert '"auto_wait": true' in out.lower()
    assert "companion_socket_wait" in out


def test_companion_task_complete_auto_wait_disabled():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.complete_task",
        return_value={"ok": True, "task_id": "abc"},
    ), patch(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        return_value={"ok": True, "running": True, "cursor_online": True},
    ), patch(
        "hui_mcp.tools.handlers.handle_companion_socket_wait",
    ) as mock_wait:
        out = handle_companion_task_complete(
            ctx,
            {"task_id": "abc", "reply": "done", "auto_wait": False},
        )
    mock_wait.assert_not_called()
    assert '"auto_wait"' not in out


def test_companion_connection_status_proxies_daemon_health():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.connection_status",
        return_value={"ok": True, "agent": {"cursor_online": True}},
    ):
        out = handle_companion_connection_status(ctx, {})
    assert '"cursor_online": true' in out.lower()
