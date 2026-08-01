"""Tests for companion_socket_wait."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.context import AppContext
from hui_mcp.cursor_socket_manager import (
    DEFAULT_WAIT_TIMEOUT_SEC,
    resolve_wait_timeout_sec,
    wait_for_task,
)
from hui_mcp.tools.handlers import handle_companion_socket_wait


def test_resolve_wait_timeout_default_12h():
    assert resolve_wait_timeout_sec(None) == DEFAULT_WAIT_TIMEOUT_SEC
    assert DEFAULT_WAIT_TIMEOUT_SEC == 720 * 60


def test_resolve_wait_timeout_respects_custom_watch():
    assert resolve_wait_timeout_sec(None, watch_minutes=30) == 30 * 60
    assert resolve_wait_timeout_sec(999999, watch_minutes=30) == 30 * 60


def test_wait_for_task_caps_by_remaining(tmp_path, monkeypatch):
    wait_file = tmp_path / "cursor-wait-state.json"
    monkeypatch.setattr("hui_mcp.cursor_socket_manager.WAIT_STATE_FILE", wait_file)

    def fake_pending():
        return {"ok": True, "pending": None, "voice_pending": None}

    monkeypatch.setattr("hui_mcp.daemon_client.notify_wait_state", lambda _: {"ok": True})
    monkeypatch.setattr(
        "hui_mcp.cursor_socket_manager.get_watch_status",
        lambda: {"cursor_online": True, "running": True, "remaining_sec": 0},
    )
    monkeypatch.setattr("hui_mcp.daemon_client.get_pending", fake_pending)
    result = wait_for_task(timeout_sec=3600, poll_interval=0.5)
    assert result["reason"] == "watch_expired"


def test_cursor_wait_state_file(tmp_path, monkeypatch):
    wait_file = tmp_path / "cursor-wait-state.json"
    monkeypatch.setattr("hui_mcp.cursor_socket_manager.WAIT_STATE_FILE", wait_file)
    monkeypatch.setattr("hui_mcp.daemon_client.notify_wait_state", lambda _: {"ok": True})
    from hui_mcp.cursor_socket_manager import begin_cursor_wait, end_cursor_wait, read_watch_metadata

    begin_cursor_wait()
    assert read_watch_metadata()["cursor_waiting"] is True
    end_cursor_wait()
    assert read_watch_metadata()["cursor_waiting"] is False


def test_socket_wait_returns_pending():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.wait_for_task",
        return_value={
            "ok": True,
            "task_received": True,
            "pending": {"task_id": "t1", "text": "hi"},
            "watch": {"remaining_sec": 100},
        },
    ):
        out = handle_companion_socket_wait(ctx, {"timeout_sec": 5})
    assert "task_received" in out or "t1" in out


def test_socket_wait_default_timeout_12h():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.wait_for_task",
    ) as mock_wait:
        mock_wait.return_value = {"ok": True, "task_received": False, "continue_waiting": True}
        handle_companion_socket_wait(ctx, {})
    mock_wait.assert_called_once()
    assert mock_wait.call_args.kwargs["timeout_sec"] == DEFAULT_WAIT_TIMEOUT_SEC


def test_socket_wait_continue():
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    with patch(
        "hui_mcp.cursor_socket_manager.wait_for_task",
        return_value={
            "ok": True,
            "task_received": False,
            "continue_waiting": True,
            "reason": "poll_timeout",
            "watch": {"remaining_sec": 200},
        },
    ):
        out = handle_companion_socket_wait(ctx, {})
    assert "companion_socket_wait" in out
