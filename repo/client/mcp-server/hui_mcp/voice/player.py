"""Play MP3 audio cross-platform."""

from __future__ import annotations

import platform
import subprocess
import tempfile
from pathlib import Path

_play_proc: subprocess.Popen | None = None


def stop() -> None:
    global _play_proc
    if _play_proc is not None and _play_proc.poll() is None:
        _play_proc.terminate()
        try:
            _play_proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _play_proc.kill()
    _play_proc = None


def is_playing() -> bool:
    global _play_proc
    return _play_proc is not None and _play_proc.poll() is None


def play_mp3(data: bytes) -> subprocess.Popen:
    """Play MP3 bytes; returns subprocess (caller may wait)."""
    global _play_proc
    stop()
    fd, path = tempfile.mkstemp(suffix=".mp3")
    import os

    os.close(fd)
    p = Path(path)
    p.write_bytes(data)
    system = platform.system()
    if system == "Darwin":
        _play_proc = subprocess.Popen(["afplay", str(p)])
    elif system == "Windows":
        _play_proc = subprocess.Popen(
            ["powershell", "-c", f'(New-Object Media.SoundPlayer "{p}").PlaySync()'],
        )
    else:
        _play_proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", str(p)])
    return _play_proc
