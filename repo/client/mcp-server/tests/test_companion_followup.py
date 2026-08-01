"""Tests for companion follow-up reading policy."""

from __future__ import annotations

from hui_mcp.companion_followup import (
    build_doc_read_followup,
    build_doc_read_followup_foreground,
    build_followup_message,
    build_voice_followup,
)
from hui_mcp.agent.doc_read_worker import is_doc_read_task


def test_doc_read_followup_foreground_mode():
    msg = build_doc_read_followup_foreground("t1", "完整阅读第四节并总结")
    assert "get_screenshot" in msg
    assert "先思考" in msg
    assert "禁止猛滚到底" in msg
    assert "companion_socket_wait" in msg


def test_voice_followup_includes_duplex():
    msg = build_voice_followup(
        "u1",
        "用中文阅读",
        {"ack_text": "好的", "speak_segments": ["好的"], "executed_actions": []},
    )
    assert "双工" in msg
    assert "u1" in msg
    assert "勿重复" in msg


def test_doc_read_followup_default_uses_agent_read():
    msg = build_followup_message(
        {"task_id": "t1", "text": "完整阅读第四节并总结"},
        None,
    )
    assert msg is not None
    assert "get_screenshot" in msg
    assert "keyboard_press" in msg or "mouse_scroll" in msg


def test_doc_read_followup_cli_args():
    from hui_mcp.companion_followup import main

    import io
    import sys

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--task-id", "abc", "--text", "完整阅读第四节并总结"])
    finally:
        sys.stdout = old
    assert code == 0
    out = buf.getvalue()
    assert "abc" in out
    assert "get_screenshot" in out


def test_is_doc_read_task_markdown_path():
    ok, section = is_doc_read_task("阅读/Users/bryan.ren/faco/task/hui-agent/README.md并总结")
    assert ok is True
    assert section is None
