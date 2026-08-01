"""Tests for Esc / HTTP task cancellation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.task_cancel import TaskCancelController, cancel_task, get_task_cancel


def test_begin_and_cancel_signal():
    ctrl = TaskCancelController()
    ctrl.begin("t1")
    assert ctrl.is_active()
    assert not ctrl.is_cancelled()

    with patch("hui_mcp.task_cancel.cancel_task", return_value={"ok": True}) as mock_cancel:
        out = ctrl.signal(reason="用户按 Esc 终止")
    mock_cancel.assert_called_once_with("t1", reason="用户按 Esc 终止")
    assert out["ok"] is True


def test_suppress_esc_after_programmatic_esc():
    ctrl = TaskCancelController()
    ctrl.begin("t1")
    ctrl.suppress_esc_cancel(0.5)
    assert not ctrl._esc_allowed()


def test_cancel_task_completes_relay(monkeypatch):
    relay = MagicMock()
    relay.get_pending.return_value = {"task_id": "abc", "text": "x"}
    relay.complete_task.return_value = True
    store = MagicMock()
    store.get.return_value = MagicMock(status="running")

    monkeypatch.setattr("hui_mcp.cursor_relay.get_relay", lambda: relay)
    monkeypatch.setattr("hui_mcp.agent.doc_read_store.get_doc_read_store", lambda: store)
    monkeypatch.setattr(
        "hui_mcp.agent.doc_read_store.load_doc_read_snapshot",
        lambda _tid: store.get.return_value,
    )
    monkeypatch.setattr("hui_mcp.active_task_store.clear_active_task", lambda: None)
    monkeypatch.setattr("hui_mcp.notify.macos_notify", lambda *a, **k: None)

    get_task_cancel().begin("abc")
    out = cancel_task("abc", reason="用户按 Esc 终止")
    assert out["ok"] is True
    relay.complete_task.assert_called_once_with("abc", reply="用户按 Esc 终止", ok=False)
    assert not get_task_cancel().is_active()


def test_cancel_active_finds_voice_pending(monkeypatch):
    voice = MagicMock()
    voice.has_active_turn.return_value = True
    voice.get_pending.return_value = {
        "utterance_id": "v123",
        "text": "阅读当前",
    }
    voice.cancel_turn.return_value = True

    monkeypatch.setattr("hui_mcp.voice_relay.get_voice_relay", lambda: voice)
    monkeypatch.setattr("hui_mcp.notify.macos_notify", lambda *a, **k: None)

    get_task_cancel().clear()
    from hui_mcp.task_cancel import cancel_active

    out = cancel_active(reason="用户按 Esc 终止")
    assert out["ok"] is True
    assert out["channel"] == "voice"
    voice.cancel_turn.assert_called_once_with("v123", reason="用户按 Esc 终止")
