"""Speech-to-text — Companion Web Speech primary; optional google backend for MCP."""

from __future__ import annotations

from dataclasses import dataclass

from hui_mcp.config import SttConfig


@dataclass
class SttResult:
    ok: bool
    text: str = ""
    confidence: float = 0.0
    engine: str = ""
    error: str = ""
    message: str = ""


def listen_once(cfg: SttConfig) -> SttResult:
    """Block until one utterance or timeout."""
    engine = (cfg.engine or "web").lower()
    if engine == "web":
        return SttResult(
            ok=False,
            error="STT_WEB_ONLY",
            message="Companion 电话模式使用 Web Speech；MCP stt_listen 请设置 stt.engine=google",
        )
    if engine == "google":
        return _listen_google(cfg)
    return SttResult(
        ok=False,
        error="STT_ENGINE_UNKNOWN",
        message=f"未知 STT 引擎：{engine}",
    )


def _listen_google(cfg: SttConfig) -> SttResult:
    try:
        import speech_recognition as sr
    except ImportError:
        return SttResult(
            ok=False,
            error="STT_MISSING_DEPS",
            message="请安装 SpeechRecognition 与 PyAudio：pip install SpeechRecognition PyAudio",
        )

    timeout_s = max(1.0, cfg.timeout_ms / 1000.0)
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.25)
            audio = recognizer.listen(
                source,
                timeout=timeout_s,
                phrase_time_limit=min(30.0, timeout_s * 3),
            )
    except sr.WaitTimeoutError:
        return SttResult(ok=False, error="TIMEOUT", message="未检测到语音")
    except OSError as e:
        return SttResult(
            ok=False,
            error="MIC_UNAVAILABLE",
            message=f"麦克风不可用：{e}",
        )

    try:
        text = recognizer.recognize_google(audio, language=cfg.language)
    except sr.UnknownValueError:
        return SttResult(ok=False, error="NO_SPEECH", message="未能识别语音内容")
    except sr.RequestError as e:
        return SttResult(ok=False, error="STT_REQUEST_FAILED", message=str(e))

    text = (text or "").strip()
    if not text:
        return SttResult(ok=False, error="EMPTY", message="识别结果为空")
    return SttResult(ok=True, text=text, confidence=0.85, engine="google")
