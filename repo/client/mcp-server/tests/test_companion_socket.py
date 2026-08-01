"""Tests for MCP-driven Cursor socket watch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.context import AppContext
from hui_mcp.tools.handlers import (
    handle_companion_connection_status,
    handle_companion_socket_connect,
    handle_companion_socket_disconnect,
)


def test_companion_socket_connect_proxies_manager():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.start_watch",
        return_value={"ok": True, "cursor_online": True, "watch_minutes": 720},
    ) as mock_start:
        out = handle_companion_socket_connect(ctx, {})
    mock_start.assert_called_once_with(watch_minutes=720.0)
    assert '"cursor_online": true' in out.lower()
    assert "companion_socket_disconnect" in out


def test_companion_socket_connect_custom_watch_minutes():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.start_watch",
        return_value={"ok": True, "cursor_online": True, "watch_minutes": 30},
    ) as mock_start:
        handle_companion_socket_connect(ctx, {"watch_minutes": 30})
    mock_start.assert_called_once_with(watch_minutes=30.0)


def test_companion_socket_disconnect():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.stop_watch",
        return_value={"ok": True, "stopped": True},
    ) as mock_stop:
        out = handle_companion_socket_disconnect(ctx, {})
    mock_stop.assert_called_once_with(force=False)
    assert '"stopped": true' in out.lower()


def test_connection_status_includes_watch_fields():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.daemon_client.connection_status",
        return_value={"ok": True, "agent": {"cursor_online": False, "companion_online": True}},
    ), patch(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        return_value={"ok": True, "running": True, "remaining_sec": 120, "expires_at": "x"},
    ):
        out = handle_companion_connection_status(ctx, {})
    assert "watch_remaining_sec" in out
