"""Tests for doc read handoff coordination."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.agent.doc_read_handoff import clear, mark_ready, wait_ready


def test_handoff_mark_and_wait(tmp_path, monkeypatch):
    monkeypatch.setattr("hui_mcp.agent.doc_read_handoff.HANDOFF_DIR", tmp_path)
    clear("t1")
    assert wait_ready("t1", timeout=0.2) is False
    mark_ready("t1")
    assert wait_ready("t1", timeout=0.5) is True
    clear("t1")
    assert wait_ready("t1", timeout=0.2) is False
