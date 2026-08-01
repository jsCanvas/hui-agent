"""Companion microphone STT session — PTT records until release; continuous uses background phrases."""

from __future__ import annotations

import io
import logging
import threading
import time
from collections import deque

log = logging.getLogger("hui_mcp.voice.stt_session")

_session: CompanionSttSession | None = None

# Safety cap for a single PTT hold (seconds).
_PTT_MAX_RECORD_SEC = 60.0


class CompanionSttSession:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_fn = None
        self._listening = False
        self._continuous = False
        self._pending: deque[str] = deque()
        self._last_error = ""
        self._language = "zh-CN"
        self._recognizer = None
        self._record_stop = threading.Event()
        self._record_thread: threading.Thread | None = None
        self._recorded_audio = None
        self._record_started_at = 0.0

    @property
    def listening(self) -> bool:
        with self._lock:
            return self._listening

    def start(self, *, language: str = "zh-CN", continuous: bool = False) -> dict:
        with self._lock:
            if self._listening:
                return {"ok": True, "already": True, "listening": True}
            self._language = language or "zh-CN"
            self._continuous = bool(continuous)
            self._pending.clear()
            self._last_error = ""
            self._recorded_audio = None

        try:
            import speech_recognition as sr
        except ImportError:
            return {
                "ok": False,
                "error": "STT_MISSING_DEPS",
                "message": "请安装 SpeechRecognition 与 PyAudio：pip install SpeechRecognition PyAudio",
            }

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        try:
            source = sr.Microphone()
        except OSError as e:
            return {
                "ok": False,
                "error": "MIC_UNAVAILABLE",
                "message": f"麦克风不可用：{e}",
            }

        if continuous:
            return self._start_continuous(recognizer, source)
        return self._start_ptt(recognizer, source)

    def _start_ptt(self, recognizer, source) -> dict:
        self._recognizer = recognizer
        self._record_stop.clear()
        self._record_started_at = time.monotonic()

        def _record_loop() -> None:
            import speech_recognition as sr

            frames = io.BytesIO()
            try:
                with source as src:
                    recognizer.adjust_for_ambient_noise(src, duration=0.2)
                    while not self._record_stop.is_set():
                        elapsed = time.monotonic() - self._record_started_at
                        if elapsed >= _PTT_MAX_RECORD_SEC:
                            break
                        try:
                            buffer = src.stream.read(src.CHUNK)
                        except Exception as e:
                            with self._lock:
                                if not self._last_error:
                                    self._last_error = str(e)
                            break
                        if not buffer:
                            break
                        frames.write(buffer)
                frame_data = frames.getvalue()
                if frame_data:
                    self._recorded_audio = sr.AudioData(
                        frame_data,
                        source.SAMPLE_RATE,
                        source.SAMPLE_WIDTH,
                    )
            except Exception as e:
                log.exception("ptt record failed")
                with self._lock:
                    self._last_error = str(e)
            finally:
                frames.close()

        thread = threading.Thread(target=_record_loop, daemon=True, name="companion-ptt-stt")
        thread.start()

        with self._lock:
            self._record_thread = thread
            self._listening = True
        return {"ok": True, "listening": True, "engine": "google", "continuous": False, "mode": "ptt"}

    def _start_continuous(self, recognizer, source) -> dict:
        import speech_recognition as sr

        def _callback(rec: sr.Recognizer, audio: sr.AudioData) -> None:
            try:
                text = (rec.recognize_google(audio, language=self._language) or "").strip()
            except sr.UnknownValueError:
                return
            except sr.RequestError as e:
                with self._lock:
                    self._last_error = str(e)
                log.warning("google stt failed: %s", e)
                return
            if not text:
                return
            with self._lock:
                self._pending.append(text)
            log.info("stt phrase: %s", text[:80])

        try:
            with source as src:
                recognizer.adjust_for_ambient_noise(src, duration=0.3)
            stop_fn = recognizer.listen_in_background(
                source,
                _callback,
                phrase_time_limit=30,
            )
        except Exception as e:
            log.exception("stt start failed")
            return {"ok": False, "error": "STT_START_FAILED", "message": str(e)}

        with self._lock:
            self._stop_fn = stop_fn
            self._listening = True
        return {"ok": True, "listening": True, "engine": "google", "continuous": True, "mode": "continuous"}

    def stop(self) -> dict:
        continuous = False
        with self._lock:
            continuous = self._continuous
            self._listening = False

        if continuous:
            return self._stop_continuous()
        return self._stop_ptt()

    def _stop_continuous(self) -> dict:
        stop_fn = None
        with self._lock:
            stop_fn = self._stop_fn
            self._stop_fn = None
            texts = list(self._pending)
            self._pending.clear()
            err = self._last_error
            self._last_error = ""

        if stop_fn:
            try:
                stop_fn(wait_for_stop=False)
            except Exception:
                log.exception("stt stop failed")

        merged = " ".join(t.strip() for t in texts if t.strip()).strip()
        if err and not merged:
            return {"ok": False, "error": "STT_REQUEST_FAILED", "message": err}
        if not merged:
            return {"ok": False, "error": "NO_SPEECH", "message": "未识别到语音"}
        return {"ok": True, "text": merged, "engine": "google"}

    def _stop_ptt(self) -> dict:
        import speech_recognition as sr

        self._record_stop.set()
        thread = self._record_thread
        recognizer = self._recognizer
        language = self._language

        with self._lock:
            self._record_thread = None
            self._recognizer = None
            err = self._last_error
            self._last_error = ""

        if thread and thread.is_alive():
            thread.join(timeout=5.0)

        audio = self._recorded_audio
        self._recorded_audio = None

        if err and audio is None:
            return {"ok": False, "error": "STT_REQUEST_FAILED", "message": err}
        if audio is None:
            return {"ok": False, "error": "NO_SPEECH", "message": "未识别到语音"}

        if not recognizer:
            return {"ok": False, "error": "STT_NOT_STARTED", "message": "语音识别未启动"}

        try:
            text = (recognizer.recognize_google(audio, language=language) or "").strip()
        except sr.UnknownValueError:
            return {"ok": False, "error": "NO_SPEECH", "message": "未识别到语音"}
        except sr.RequestError as e:
            return {"ok": False, "error": "STT_REQUEST_FAILED", "message": str(e)}

        if not text:
            return {"ok": False, "error": "NO_SPEECH", "message": "未识别到语音"}

        log.info("stt ptt final: %s", text[:120])
        return {"ok": True, "text": text, "engine": "google", "mode": "ptt"}

    def poll(self) -> dict:
        with self._lock:
            if not self._pending:
                err = self._last_error
                self._last_error = ""
                if err:
                    return {"ok": False, "error": "STT_REQUEST_FAILED", "message": err}
                return {"ok": True, "texts": []}
            texts = list(self._pending)
            self._pending.clear()
            err = self._last_error
            self._last_error = ""
        return {"ok": True, "texts": texts, "error": err or None}


def get_stt_session() -> CompanionSttSession:
    global _session
    if _session is None:
        _session = CompanionSttSession()
    return _session
