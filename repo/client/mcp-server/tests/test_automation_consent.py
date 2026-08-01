"""Tests for automation consent gate."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hui_mcp.automation_consent import (
    AutomationConsentManager,
    ensure_automation_consent,
    is_input_automation_tool,
)
from hui_mcp.config import AppConfig, AutomationConfig


@pytest.fixture(autouse=True)
def _require_automation_consent(monkeypatch):
    cfg = AppConfig()
    cfg.automation = AutomationConfig(require_consent=True, consent_timeout_sec=2)
    monkeypatch.setattr("hui_mcp.config.AppConfig.load", lambda: cfg)


def test_is_input_automation_tool():
    assert is_input_automation_tool("mouse_scroll") is True
    assert is_input_automation_tool("get_screenshot") is False


def test_consent_granted_once_per_scope():
    mgr = AutomationConsentManager()
    sent: list[dict] = []
    mgr.set_companion_notify(lambda payload: sent.append(payload))

    ctx = MagicMock()
    ctx.config = AppConfig()
    ctx.config.automation = AutomationConfig(require_consent=True, consent_timeout_sec=2)

    import threading

    def approve():
        assert sent
        rid = sent[0]["request_id"]
        mgr.resolve(rid, granted=True)

    threading.Timer(0.05, approve).start()
    blocked = mgr.ensure(ctx, "mouse_click")
    assert blocked is None
    assert mgr.ensure(ctx, "mouse_click") is None


def test_consent_denied_returns_error(monkeypatch):
    mgr = AutomationConsentManager()
    sent: list[dict] = []
    mgr.set_companion_notify(lambda payload: sent.append(payload))

    ctx = MagicMock()
    ctx.config = AppConfig()
    ctx.config.automation = AutomationConfig(require_consent=True, consent_timeout_sec=2)

    monkeypatch.setattr(
        "hui_mcp.automation_consent.get_automation_consent",
        lambda: mgr,
    )
    monkeypatch.setattr(
        "hui_mcp.task_cancel.cancel_active",
        lambda **_: {"ok": True, "cancelled": True},
    )

    import threading

    def deny():
        assert sent
        mgr.resolve(sent[0]["request_id"], granted=False)

    threading.Timer(0.05, deny).start()
    out = ensure_automation_consent(ctx, "mouse_scroll")
    assert out is not None
    assert out["ok"] is False
    assert out["error"]["code"] == "AUTOMATION_DENIED"


def test_consent_delegates_to_daemon_when_no_notify(monkeypatch):
    calls: list[str] = []

    def fake_request(tool: str, *, timeout: float = 130) -> dict:
        calls.append(tool)
        return {"ok": True, "granted": True}

    monkeypatch.setattr(
        "hui_mcp.daemon_client.request_automation_consent",
        fake_request,
    )

    mgr = AutomationConsentManager()
    ctx = MagicMock()
    ctx.config = AppConfig()
    ctx.config.automation = AutomationConfig(require_consent=True, consent_timeout_sec=2)

    blocked = mgr.ensure(ctx, "mouse_move")
    assert blocked is None
    assert calls == ["mouse_move"]
