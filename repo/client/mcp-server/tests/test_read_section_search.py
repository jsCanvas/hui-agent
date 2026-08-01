"""Tests for clipboard-based section search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.agent.read_section_flow import search_section


def test_search_section_uses_clipboard_on_mac(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    def tool(name: str, args: dict | None = None) -> dict:
        calls.append((name, args))
        return {"ok": True, "result": {"width": 1440, "height": 900}}

    monkeypatch.setattr("hui_mcp.agent.read_section_flow.platform.system", lambda: "Darwin")
    monkeypatch.setattr("hui_mcp.agent.read_section_flow.activate_document_app", lambda **_: "Chrome")
    with patch("hui_mcp.agent.read_section_flow.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok, err = search_section(tool, "第四节", lambda _s, _m: None)
    assert ok is True
    assert err is None
    mock_run.assert_called()
    assert ("keyboard_hotkey", {"keys": ["cmd", "v"]}) in calls
