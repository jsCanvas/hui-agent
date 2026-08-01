"""Tests for duplex voice router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.agent.intents import IntentKind
from hui_mcp.config import AppConfig, VoiceDuplexConfig
from hui_mcp.voice.duplex_router import (
    _unique_segments,
    build_duplex_plan,
    handle_voice_duplex,
)
from hui_mcp.voice_relay import VoiceRelay


def test_build_duplex_plan_read_defers():
    cfg = AppConfig()
    cfg.voice = VoiceDuplexConfig(enabled=True)
    plan = build_duplex_plan("用中文阅读这篇小说", cfg)
    assert plan.defer_to_cursor is True
    assert plan.ack_text
    assert len(plan.speak_segments) >= 1
    assert any(a.tool == "get_screen_info" for a in plan.simple_actions)


def test_build_duplex_plan_scroll_edge_only():
    cfg = AppConfig()
    plan = build_duplex_plan("向下滚动", cfg)
    assert plan.defer_to_cursor is False
    assert plan.intent == IntentKind.SCROLL_DOWN.value
    assert any(a.tool == "mouse_scroll" for a in plan.simple_actions)


def test_handle_voice_duplex_edge_only_completes():
    relay = VoiceRelay()
    relay.start_session()
    speaks: list[dict] = []

    def notify(payload: dict) -> None:
        speaks.append(payload)
        sid = payload.get("speak_id")
        if sid:
            relay.notify_speak_done(str(sid))

    relay.set_notify_companion(notify)
    ctx = MagicMock()
    ctx.config = AppConfig()
    ctx.config.voice = VoiceDuplexConfig(enabled=True)

    with patch("hui_mcp.voice.duplex_router.execute_simple_actions", return_value=[]):
        with patch("hui_mcp.voice_relay.get_voice_relay", return_value=relay):
            out = handle_voice_duplex(ctx, "帮助")

    assert out.get("ok") is True
    assert out.get("edge_only") is True
    assert relay.get_pending() is None
    assert speaks


def test_unique_segments_dedupes_ack():
    cfg = AppConfig()
    plan = build_duplex_plan("向下滚动", cfg)
    segs = _unique_segments(plan)
    assert len(segs) == 1
    assert segs[0] == plan.ack_text


def test_edge_only_speaks_each_line_once():
    relay = VoiceRelay()
    relay.start_session()
    texts: list[str] = []

    def notify(payload: dict) -> None:
        texts.append(str(payload.get("text") or ""))
        sid = payload.get("speak_id")
        if sid:
            relay.notify_speak_done(str(sid))

    relay.set_notify_companion(notify)
    ctx = MagicMock()
    ctx.config = AppConfig()
    ctx.config.voice = VoiceDuplexConfig(enabled=True)

    with patch("hui_mcp.voice.duplex_router.execute_simple_actions", return_value=[]):
        with patch("hui_mcp.voice_relay.get_voice_relay", return_value=relay):
            handle_voice_duplex(ctx, "帮助")

    assert texts.count(texts[0]) == 1 if texts else True
    assert len(texts) == len(set(texts))
