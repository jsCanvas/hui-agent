"""Tests for companion_socket_connect_and_wait."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.context import AppContext
from hui_mcp.tools.handlers import handle_companion_socket_connect_and_wait


def test_connect_and_wait_when_offline():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        return_value={"cursor_online": False, "running": False},
    ), patch(
        "hui_mcp.cursor_socket_manager.start_watch",
        return_value={"ok": True, "cursor_online": True, "watch_minutes": 720},
    ) as mock_start, patch(
        "hui_mcp.tools.handlers.handle_companion_socket_wait",
        return_value='{"ok": true, "task_received": false, "continue_waiting": true, "message": "监听中"}',
    ) as mock_wait:
        out = handle_companion_socket_connect_and_wait(ctx, {"poll_interval_sec": 2})
    mock_start.assert_called_once_with(watch_minutes=720.0)
    mock_wait.assert_called_once()
    assert "connect" in out
    assert "Socket 已连接" in out
    assert "companion_socket_wait" in out or "continue_waiting" in out


def test_connect_and_wait_skips_connect_when_online():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        return_value={"cursor_online": True, "running": True, "remaining_sec": 100},
    ), patch(
        "hui_mcp.cursor_socket_manager.start_watch",
    ) as mock_start, patch(
        "hui_mcp.tools.handlers.handle_companion_socket_wait",
        return_value='{"ok": true, "continue_waiting": true, "agent_next": "companion_socket_wait", "message": "监听中"}',
    ):
        out = handle_companion_socket_connect_and_wait(ctx, {})
    mock_start.assert_not_called()
    assert "skipped_connect" in out or "Socket 已在线" in out
