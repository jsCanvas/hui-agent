"""PTT STT session — record until release, recognize once."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from hui_mcp.voice.stt_session import CompanionSttSession


class _FakeMic:
    SAMPLE_RATE = 16000
    SAMPLE_WIDTH = 2
    CHUNK = 1024

    def __init__(self) -> None:
        self.stream = self
        self._reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, chunk_size):
        self._reads += 1
        if self._reads > 3:
            time.sleep(0.02)
            return b"\x00" * chunk_size
        return b"\x01" * chunk_size


def test_ptt_stop_recognizes_full_buffer_once():
    session = CompanionSttSession()
    fake_recognizer = MagicMock()
    fake_recognizer.recognize_google.return_value = "阅读当前页面内容"
    session._recognizer = fake_recognizer
    session._language = "zh-CN"
    session._recorded_audio = sr.AudioData(b"\x01" * 2048, 16000, 2)
    session._record_stop.set()

    out = session._stop_ptt()
    assert out["ok"] is True
    assert out["text"] == "阅读当前页面内容"
    fake_recognizer.recognize_google.assert_called_once()


def test_ptt_does_not_use_listen_in_background():
    session = CompanionSttSession()
    fake_recognizer = MagicMock()
    fake_mic = _FakeMic()

    with patch("speech_recognition.Microphone", return_value=fake_mic):
        with patch("speech_recognition.Recognizer", return_value=fake_recognizer):
            out = session.start(language="zh-CN", continuous=False)

    assert out["ok"] is True
    assert out.get("mode") == "ptt"
    fake_recognizer.listen_in_background.assert_not_called()
    assert session._record_thread is not None

    out = session.stop()
    assert out.get("ok") or out.get("error") in ("NO_SPEECH", "STT_REQUEST_FAILED")


def test_continuous_still_uses_background_listener():
    session = CompanionSttSession()
    fake_recognizer = MagicMock()
    fake_recognizer.listen_in_background.return_value = MagicMock()
    fake_mic = MagicMock()
    fake_mic.__enter__ = MagicMock(return_value=fake_mic)
    fake_mic.__exit__ = MagicMock(return_value=False)

    with patch("speech_recognition.Microphone", return_value=fake_mic):
        with patch("speech_recognition.Recognizer", return_value=fake_recognizer):
            out = session.start(language="zh-CN", continuous=True)

    assert out["ok"] is True
    assert out.get("mode") == "continuous"
    fake_recognizer.listen_in_background.assert_called_once()
