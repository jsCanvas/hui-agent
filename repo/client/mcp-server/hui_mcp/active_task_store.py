"""Persisted Companion task files under ~/.hui-agent (written by cursor-socket-client)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ACTIVE_TASK = Path.home() / ".hui-agent" / "active-task.json"
ACTIVE_VOICE = Path.home() / ".hui-agent" / "active-voice.json"


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def read_active_task() -> dict[str, str] | None:
    data = _read_json(ACTIVE_TASK)
    if not data:
        return None
    if (data.get("channel") or "").strip().lower() == "voice":
        return None
    task_id = (data.get("task_id") or "").strip()
    text = (data.get("text") or "").strip()
    if task_id and text:
        return {"task_id": task_id, "text": text}
    return None


def read_active_voice() -> dict[str, Any] | None:
    data = _read_json(ACTIVE_VOICE)
    if not data:
        return None
    utterance_id = (data.get("utterance_id") or "").strip()
    text = (data.get("text") or "").strip()
    if not utterance_id or not text:
        return None
    out: dict[str, Any] = {
        "utterance_id": utterance_id,
        "text": text,
    }
    session_id = (data.get("session_id") or "").strip()
    if session_id:
        out["session_id"] = session_id
    duplex = data.get("duplex")
    if isinstance(duplex, dict):
        out["duplex"] = duplex
    return out


def clear_active_task() -> None:
    try:
        ACTIVE_TASK.unlink(missing_ok=True)
    except OSError:
        pass


def clear_active_voice() -> None:
    try:
        ACTIVE_VOICE.unlink(missing_ok=True)
    except OSError:
        pass


def clear_task_artifacts(task_id: str) -> None:
    """Remove persisted pending files for a completed task or utterance."""
    task_id = (task_id or "").strip()
    if not task_id:
        return
    voice = read_active_voice()
    if voice and voice.get("utterance_id") == task_id:
        clear_active_voice()
    task = _read_json(ACTIVE_TASK)
    if task and (task.get("task_id") or "").strip() == task_id:
        clear_active_task()
