"""Voice relay tests."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.voice_relay import VoiceRelay


def test_submit_and_complete_turn():
    relay = VoiceRelay()
    relay.start_session()
    sent: list[dict] = []
    relay.set_notify_cursor(lambda p: sent.append(p))

    with patch("hui_mcp.cursor_relay.get_relay") as mock_get:
        mock_get.return_value.is_cursor_online.return_value = True
        out = relay.submit_utterance("你好")
    assert out["ok"] is True
    uid = out["utterance_id"]
    assert sent[0]["type"] == "voice.user.message"
    assert sent[0]["text"] == "你好"

    pending = relay.get_pending()
    assert pending is not None
    assert pending["utterance_id"] == uid

    assert relay.complete_turn(uid, reply="你好，我在", ok=True) is True
    assert relay.get_pending() is None


def test_speak_to_companion():
    relay = VoiceRelay()
    relay.start_session()
    speaks: list[dict] = []

    def notify(payload: dict) -> None:
        speaks.append(payload)
        speak_id = payload.get("speak_id")
        if speak_id:
            relay.notify_speak_done(str(speak_id))

    relay.set_notify_companion(notify)

    out = relay.speak("第一段", final=False)
    assert out["ok"] is True
    assert out.get("playback_done") is True
    assert speaks[0]["type"] == "voice.speak"
    assert speaks[0]["text"] == "第一段"
    assert speaks[0]["speak_id"]


def test_speak_interrupt_releases_pending():
    relay = VoiceRelay()
    relay.start_session()
    pending_id: list[str] = []

    def notify(payload: dict) -> None:
        sid = payload.get("speak_id")
        if sid:
            pending_id.append(str(sid))
            if payload.get("interrupt"):
                relay.notify_speak_done(str(sid))

    relay.set_notify_companion(notify)

    import threading

    done = threading.Event()

    def blocked_speak() -> None:
        relay.speak("第一段很长的话", final=False)
        done.set()

    thread = threading.Thread(target=blocked_speak, daemon=True)
    thread.start()
    thread.join(timeout=0.2)
    assert pending_id, "first speak should be dispatched"

    out = relay.speak("打断", interrupt=True, final=True)
    assert out["ok"] is True
    assert done.wait(timeout=1.0)


def test_speak_offline_companion():
    relay = VoiceRelay()
    relay.start_session()
    out = relay.speak("hi")
    assert out["ok"] is False


def test_submit_fails_when_cursor_notify_raises():
    relay = VoiceRelay()
    relay.start_session()

    def boom(_payload):
        raise RuntimeError("Cursor Socket 未连接")

    relay.set_notify_cursor(boom)

    with patch("hui_mcp.cursor_relay.get_relay") as mock_get:
        mock_get.return_value.is_cursor_online.return_value = True
        out = relay.submit_utterance("你好")
    assert out["ok"] is False
    assert "Cursor Socket" in (out.get("error") or "")


def test_multi_turn_queue():
    relay = VoiceRelay()
    relay.start_session()
    relay.set_notify_cursor(lambda _p: None)

    with patch("hui_mcp.cursor_relay.get_relay") as mock_get:
        mock_get.return_value.is_cursor_online.return_value = True
        a = relay.submit_utterance("第一句")
        b = relay.submit_utterance("第二句")
    assert a["ok"] and b["ok"]
    assert a["utterance_id"] != b["utterance_id"]

    pending = relay.get_pending()
    assert pending["text"] == "第一句"
    relay.complete_turn(pending["utterance_id"], reply="ok1")
    pending2 = relay.get_pending()
    assert pending2["text"] == "第二句"


def test_cancel_turn_notifies_companion():
    relay = VoiceRelay()
    relay.start_session()
    events: list[dict] = []

    def notify(payload: dict) -> None:
        events.append(payload)
        speak_id = payload.get("speak_id")
        if speak_id:
            relay.notify_speak_done(str(speak_id))

    relay.set_notify_companion(notify)
    relay.set_notify_cursor(lambda _p: None)

    with patch("hui_mcp.cursor_relay.get_relay") as mock_get:
        mock_get.return_value.is_cursor_online.return_value = True
        out = relay.submit_utterance("阅读当前")
    uid = out["utterance_id"]

    assert relay.cancel_turn(uid, reason="用户按 Esc 终止") is True
    assert any(e.get("type") == "voice.speak" for e in events)
    assert any(
        e.get("type") == "voice.turn.done" and e.get("ok") is False for e in events
    )
    assert relay.get_pending() is None
