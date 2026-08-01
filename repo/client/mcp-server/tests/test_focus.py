"""Tests for document focus helpers."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.agent.read_section_flow import _content_hash, _document_focus_point
from hui_mcp.input.focus import activate_document_app


def test_document_focus_point():
    x, y = _document_focus_point(1440, 900)
    assert x == 460
    assert y == 378


@patch("hui_mcp.input.focus.subprocess.run")
def test_activate_document_app(mock_run):
    mock_run.return_value.stdout = "Safari\n"
    mock_run.return_value.returncode = 0
    assert activate_document_app() == "Safari"
    mock_run.assert_called_once()


@patch("hui_mcp.input.focus.subprocess.run")
def test_activate_cursor_app(mock_run):
    from hui_mcp.input.focus import activate_cursor_app

    mock_run.return_value.stdout = "Cursor\n"
    mock_run.return_value.returncode = 0
    assert activate_cursor_app() == "Cursor"


def test_content_hash_missing_file():
    assert _content_hash("/tmp/does-not-exist-hui-agent.png") is None
