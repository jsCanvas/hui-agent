"""Cursor relay tests."""

from __future__ import annotations

import threading

from hui_mcp.cursor_relay import CursorRelay


def test_run_task_offline():
    relay = CursorRelay()
    out = relay.run_task("完整阅读第四节并总结")
    assert out["ok"] is False
    assert "Socket" in out["reply"]


def test_run_task_complete():
    relay = CursorRelay()
    relay.set_cursor_online(True)
    relay.set_notify(lambda _task: None)

    result: dict = {}

    def worker():
        result["out"] = relay.run_task("完整阅读第四节并总结")

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    for _ in range(50):
        pending = relay.get_pending()
        if pending:
            break
        threading.Event().wait(0.01)

    pending = relay.get_pending()
    assert pending is not None
    assert pending["text"] == "完整阅读第四节并总结"

    ok = relay.complete_task(pending["task_id"], reply="第四节摘要：…", ok=True)
    assert ok is True
    t.join(timeout=2)
    out = result["out"]
    assert out["ok"] is True
    assert "摘要" in out["reply"]


def test_complete_unknown_task():
    relay = CursorRelay()
    assert relay.complete_task("nope", reply="x") is False
