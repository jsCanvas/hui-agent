"""Tests for cursor-socket-client trigger mode resolution."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

CLIENT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = CLIENT_ROOT / "scripts" / "cursor-socket-client.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("cursor_socket_client", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cursor_socket_client"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_resolve_cursor_trigger_mode_background_aliases():
    mod = _load_module()
    assert mod.resolve_cursor_trigger_mode({"doc_read": {"cursor_trigger": "notify"}}) == "background"
    assert mod.resolve_cursor_trigger_mode({"doc_read": {"cursor_trigger": "background"}}) == "background"


def test_resolve_cursor_trigger_mode_notify_only():
    mod = _load_module()
    assert mod.resolve_cursor_trigger_mode({"doc_read": {"cursor_trigger": "notify_only"}}) == "notify_only"


def test_resolve_cursor_trigger_mode_notify_only_default():
    mod = _load_module()
    assert mod.resolve_cursor_trigger_mode({}) == "notify_only"


def test_resolve_cursor_trigger_mode_osascript():
    mod = _load_module()
    assert mod.resolve_cursor_trigger_mode({"doc_read": {"cursor_trigger": "osascript"}}) == "osascript"
