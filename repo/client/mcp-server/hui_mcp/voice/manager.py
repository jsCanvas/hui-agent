"""Manage Edge TTS proxy subprocess lifecycle."""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

from hui_mcp.voice.tts_client import TtsClient

if TYPE_CHECKING:
    from hui_mcp.config import AppConfig

_proxy_proc: subprocess.Popen | None = None


def ensure_proxy(cfg: AppConfig, timeout: float = 15.0) -> None:
    """Start tts_proxy if not healthy."""
    global _proxy_proc
    client = TtsClient(cfg.tts)
    if client.health():
        return
    if _proxy_proc is not None and _proxy_proc.poll() is None:
        _wait_healthy(client, timeout)
        return

    env = {
        **dict(__import__("os").environ),
        "TTS_PROXY_PORT": str(cfg.tts.proxy_port),
        "EDGE_TTS_VOICE": cfg.tts.voice,
    }
    _proxy_proc = subprocess.Popen(
        [sys.executable, "-m", "hui_mcp.voice.tts_proxy"],
        env=env,
        stderr=subprocess.PIPE,
    )
    _wait_healthy(client, timeout)


def _wait_healthy(client: TtsClient, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.health():
            return
        time.sleep(0.3)
    raise RuntimeError("Edge TTS proxy failed to start; check network and edge-tts install")


def stop_proxy() -> None:
    global _proxy_proc
    if _proxy_proc is not None and _proxy_proc.poll() is None:
        _proxy_proc.terminate()
        try:
            _proxy_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _proxy_proc.kill()
    _proxy_proc = None
