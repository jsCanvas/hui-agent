"""Coordination between Cursor Agent trigger and background OCR worker."""

from __future__ import annotations

import time
from pathlib import Path

HANDOFF_DIR = Path.home() / ".hui-agent" / "doc-read-handoff"


def mark_ready(task_id: str) -> None:
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    (HANDOFF_DIR / f"{task_id}.ready").write_text(str(time.time()), encoding="utf-8")


def wait_ready(task_id: str, *, timeout: float = 15.0) -> bool:
    path = HANDOFF_DIR / f"{task_id}.ready"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file():
            return True
        time.sleep(0.1)
    return False


def clear(task_id: str) -> None:
    try:
        (HANDOFF_DIR / f"{task_id}.ready").unlink(missing_ok=True)
    except OSError:
        pass
