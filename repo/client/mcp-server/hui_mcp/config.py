"""Runtime configuration (~/.hui-agent/config.json + env)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("HUI_AGENT_HOME", Path.home() / ".hui-agent"))
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class TtsConfig:
    engine: str = "edge-tts"
    url: str = "http://127.0.0.1:8896"
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+10%"
    pitch: str = "+2Hz"
    volume: str = "+0%"
    proxy_port: int = 8896
    auto_start_proxy: bool = True


@dataclass
class SttConfig:
    engine: str = "web"
    language: str = "zh-CN"
    timeout_ms: int = 10000
    input_mode: str = "push_to_talk"  # push_to_talk | continuous


@dataclass
class SocketConfig:
    host: str = "127.0.0.1"
    port: int = 18765
    token: str = ""
    watch_minutes: int = 720  # 12 hours


@dataclass
class LlmConfig:
    """OpenAI-compatible vision LLM for Agent reasoning."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout_sec: int = 120
    max_steps: int = 24

    def ready(self) -> bool:
        return bool(self.api_key.strip())


@dataclass
class CursorConfig:
    """Legacy cursor settings (Socket relay no longer requires API key)."""

    api_key: str = ""
    model: str = "composer-2.5"
    workspace: str = ""
    timeout_sec: int = 600

    def ready(self) -> bool:
        return False


@dataclass
class AgentConfig:
    """Agent orchestration mode."""

    mode: str = "cursor"  # cursor | rules | llm | auto


@dataclass
class AutomationConfig:
    """Require Companion UI confirmation before mouse/keyboard automation."""

    require_consent: bool = True
    consent_timeout_sec: int = 120


@dataclass
class VoiceDuplexConfig:
    """Duplex mode: local edge instant ack + simple actions; Cursor plans full execution."""

    enabled: bool = True
    edge_tier: str = "builtin"  # builtin | gguf
    instant_speak: bool = True
    followup_speak: bool = False
    execute_simple_actions: bool = True


@dataclass
class DocReadConfig:
    """Background OCR document reader (dual-path with Cursor)."""

    enabled: bool = True
    max_pages: int = 24
    page_downs: int = 0
    scroll_dy: int = -24
    stale_hits_to_stop: int = 2
    edge_outline: bool = True
    edge_model: str = "auto"  # auto | builtin | gguf
    gguf_model_path: str = ""
    gguf_n_ctx: int = 4096
    gguf_n_threads: int = 0
    gguf_n_gpu_layers: int = 0
    gguf_max_tokens: int = 1024
    gguf_temperature: float = 0.2
    gguf_input_chars: int = 10000
    ocr_preview_chars: int = 4000
    assume_doc_foreground: bool = True
    auto_start_on_relay: bool = False  # legacy OCR Worker; default Agent-driven read
    cursor_trigger: str = "notify_only"  # notify_only | background | osascript
    notify_on_complete: bool = True
    esc_cancel_enabled: bool = True


@dataclass
class AppConfig:
    tts: TtsConfig = field(default_factory=TtsConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    socket: SocketConfig = field(default_factory=SocketConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    voice: VoiceDuplexConfig = field(default_factory=VoiceDuplexConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    doc_read: DocReadConfig = field(default_factory=DocReadConfig)
    frame_dir: Path = field(default_factory=lambda: Path("/tmp/hui-agent-frames"))

    def effective_agent_mode(self) -> str:
        mode = (self.agent.mode or "cursor").lower()
        if mode == "auto":
            if self.llm.ready():
                return "llm"
            return "cursor"
        return mode

    @classmethod
    def load(cls) -> AppConfig:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            tts_raw = raw.get("tts", {})
            stt_raw = raw.get("stt", {})
            sock_raw = raw.get("socket", {})
            llm_raw = raw.get("llm", {})
            cursor_raw = raw.get("cursor", {})
            agent_raw = raw.get("agent", {})
            voice_raw = raw.get("voice", {})
            automation_raw = raw.get("automation", {})
            doc_raw = raw.get("doc_read", {})
            token = sock_raw.get("token") or str(uuid.uuid4())
            api_key = llm_raw.get("api_key") or os.environ.get("HUI_AGENT_LLM_API_KEY", "")
            cursor_key = cursor_raw.get("api_key") or os.environ.get("CURSOR_API_KEY", "")
            return cls(
                tts=TtsConfig(
                    engine=tts_raw.get("engine", "edge-tts"),
                    url=tts_raw.get("url", os.environ.get("HUI_AGENT_TTS_URL", "http://127.0.0.1:8896")),
                    voice=tts_raw.get("voice", os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")),
                    rate=tts_raw.get("rate", "+10%"),
                    pitch=tts_raw.get("pitch", "+2Hz"),
                    volume=tts_raw.get("volume", "+0%"),
                    proxy_port=int(os.environ.get("TTS_PROXY_PORT", tts_raw.get("proxy_port", 8896))),
                    auto_start_proxy=tts_raw.get("auto_start_proxy", True),
                ),
                stt=SttConfig(
                    engine=stt_raw.get("engine", "web"),
                    language=stt_raw.get("language", "zh-CN"),
                    timeout_ms=int(stt_raw.get("timeout_ms", 10000)),
                    input_mode=stt_raw.get("input_mode", "push_to_talk"),
                ),
                socket=SocketConfig(
                    host=sock_raw.get("host", "127.0.0.1"),
                    port=int(sock_raw.get("port", 18765)),
                    token=token,
                    watch_minutes=int(sock_raw.get("watch_minutes", 720)),
                ),
                llm=LlmConfig(
                    base_url=llm_raw.get(
                        "base_url",
                        os.environ.get("HUI_AGENT_LLM_BASE_URL", "https://api.openai.com/v1"),
                    ),
                    api_key=api_key,
                    model=llm_raw.get(
                        "model",
                        os.environ.get("HUI_AGENT_LLM_MODEL", "gpt-4o-mini"),
                    ),
                    timeout_sec=int(llm_raw.get("timeout_sec", 120)),
                    max_steps=int(llm_raw.get("max_steps", 24)),
                ),
                agent=AgentConfig(mode=agent_raw.get("mode", "cursor")),
                voice=VoiceDuplexConfig(
                    enabled=bool(voice_raw.get("duplex_enabled", voice_raw.get("enabled", True))),
                    edge_tier=str(voice_raw.get("edge_tier", "builtin")),
                    instant_speak=bool(voice_raw.get("instant_speak", True)),
                    followup_speak=bool(voice_raw.get("followup_speak", False)),
                    execute_simple_actions=bool(voice_raw.get("execute_simple_actions", True)),
                ),
                automation=AutomationConfig(
                    require_consent=bool(automation_raw.get("require_consent", True)),
                    consent_timeout_sec=int(automation_raw.get("consent_timeout_sec", 120)),
                ),
                doc_read=DocReadConfig(
                    enabled=bool(doc_raw.get("enabled", True)),
                    max_pages=int(doc_raw.get("max_pages", 24)),
                    page_downs=int(doc_raw.get("page_downs", 0)),
                    scroll_dy=int(doc_raw.get("scroll_dy", -24)),
                    stale_hits_to_stop=int(doc_raw.get("stale_hits_to_stop", 2)),
                    edge_outline=bool(
                        doc_raw.get("edge_outline", doc_raw.get("edge_llm_outline", True))
                    ),
                    edge_model=str(doc_raw.get("edge_model", "auto")),
                    gguf_model_path=str(doc_raw.get("gguf_model_path", "")),
                    gguf_n_ctx=int(doc_raw.get("gguf_n_ctx", 4096)),
                    gguf_n_threads=int(doc_raw.get("gguf_n_threads", 0)),
                    gguf_n_gpu_layers=int(doc_raw.get("gguf_n_gpu_layers", 0)),
                    gguf_max_tokens=int(doc_raw.get("gguf_max_tokens", 1024)),
                    gguf_temperature=float(doc_raw.get("gguf_temperature", 0.2)),
                    gguf_input_chars=int(doc_raw.get("gguf_input_chars", 10000)),
                    ocr_preview_chars=int(doc_raw.get("ocr_preview_chars", 4000)),
                    assume_doc_foreground=bool(doc_raw.get("assume_doc_foreground", True)),
                    auto_start_on_relay=bool(doc_raw.get("auto_start_on_relay", False)),
                    cursor_trigger=str(doc_raw.get("cursor_trigger", "notify_only")),
                    notify_on_complete=bool(doc_raw.get("notify_on_complete", True)),
                    esc_cancel_enabled=bool(doc_raw.get("esc_cancel_enabled", True)),
                ),
                cursor=CursorConfig(
                    api_key=cursor_key,
                    model=cursor_raw.get(
                        "model",
                        os.environ.get("HUI_AGENT_CURSOR_MODEL", "composer-2.5"),
                    ),
                    workspace=cursor_raw.get("workspace", os.environ.get("HUI_AGENT_WORKSPACE", "")),
                    timeout_sec=int(cursor_raw.get("timeout_sec", 600)),
                ),
                frame_dir=Path(raw.get("frame_dir", "/tmp/hui-agent-frames")),
            )
        cfg = cls()
        cfg.socket.token = str(uuid.uuid4())
        cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "tts": {
                "engine": self.tts.engine,
                "url": self.tts.url,
                "voice": self.tts.voice,
                "rate": self.tts.rate,
                "pitch": self.tts.pitch,
                "volume": self.tts.volume,
                "proxy_port": self.tts.proxy_port,
                "auto_start_proxy": self.tts.auto_start_proxy,
            },
            "stt": {
                "engine": self.stt.engine,
                "language": self.stt.language,
                "timeout_ms": self.stt.timeout_ms,
                "input_mode": self.stt.input_mode,
            },
            "socket": {
                "host": self.socket.host,
                "port": self.socket.port,
                "token": self.socket.token,
                "watch_minutes": self.socket.watch_minutes,
            },
            "llm": {
                "base_url": self.llm.base_url,
                "api_key": self.llm.api_key,
                "model": self.llm.model,
                "timeout_sec": self.llm.timeout_sec,
                "max_steps": self.llm.max_steps,
            },
            "agent": {"mode": self.agent.mode},
            "voice": {
                "duplex_enabled": self.voice.enabled,
                "edge_tier": self.voice.edge_tier,
                "instant_speak": self.voice.instant_speak,
                "followup_speak": self.voice.followup_speak,
                "execute_simple_actions": self.voice.execute_simple_actions,
            },
            "automation": {
                "require_consent": self.automation.require_consent,
                "consent_timeout_sec": self.automation.consent_timeout_sec,
            },
            "doc_read": {
                "enabled": self.doc_read.enabled,
                "max_pages": self.doc_read.max_pages,
                "page_downs": self.doc_read.page_downs,
                "scroll_dy": self.doc_read.scroll_dy,
                "stale_hits_to_stop": self.doc_read.stale_hits_to_stop,
                "edge_outline": self.doc_read.edge_outline,
                "edge_model": self.doc_read.edge_model,
                "gguf_model_path": self.doc_read.gguf_model_path,
                "gguf_n_ctx": self.doc_read.gguf_n_ctx,
                "gguf_n_threads": self.doc_read.gguf_n_threads,
                "gguf_n_gpu_layers": self.doc_read.gguf_n_gpu_layers,
                "gguf_max_tokens": self.doc_read.gguf_max_tokens,
                "gguf_temperature": self.doc_read.gguf_temperature,
                "gguf_input_chars": self.doc_read.gguf_input_chars,
                "ocr_preview_chars": self.doc_read.ocr_preview_chars,
                "assume_doc_foreground": self.doc_read.assume_doc_foreground,
                "auto_start_on_relay": self.doc_read.auto_start_on_relay,
                "cursor_trigger": self.doc_read.cursor_trigger,
                "notify_on_complete": self.doc_read.notify_on_complete,
                "esc_cancel_enabled": self.doc_read.esc_cancel_enabled,
            },
            "cursor": {
                "api_key": self.cursor.api_key,
                "model": self.cursor.model,
                "workspace": self.cursor.workspace,
                "timeout_sec": self.cursor.timeout_sec,
            },
            "frame_dir": str(self.frame_dir),
        }
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
