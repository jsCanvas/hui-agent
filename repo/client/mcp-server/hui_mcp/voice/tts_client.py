"""HTTP client for Edge TTS proxy."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from hui_mcp.config import AppConfig, TtsConfig


@dataclass
class TtsResult:
    audio: bytes
    voice: str
    engine: str = "edge-tts"


class TtsClient:
    def __init__(self, cfg: TtsConfig | None = None) -> None:
        self.cfg = cfg or AppConfig.load().tts

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.cfg.url.rstrip('/')}/health", timeout=2.0)
            return r.status_code == 200 and r.json().get("engine") == "edge-tts"
        except Exception:
            return False

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        pitch: str | None = None,
        volume: str | None = None,
    ) -> TtsResult:
        payload = {
            "text": text,
            "voice": voice or self.cfg.voice,
            "rate": rate or self.cfg.rate,
            "pitch": pitch or self.cfg.pitch,
            "volume": volume or self.cfg.volume,
        }
        r = httpx.post(
            f"{self.cfg.url.rstrip('/')}/tts",
            json=payload,
            timeout=60.0,
        )
        if r.status_code != 200:
            detail = r.text
            try:
                detail = r.json().get("error", detail)
            except Exception:
                pass
            raise RuntimeError(f"TTS failed ({r.status_code}): {detail}")
        return TtsResult(audio=r.content, voice=payload["voice"])
