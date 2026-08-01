"""Active task file helpers."""

from __future__ import annotations

import json
from pathlib import Path

from hui_mcp.active_task_store import (
    ACTIVE_TASK,
    ACTIVE_VOICE,
    clear_task_artifacts,
    read_active_task,
    read_active_voice,
)


def test_read_active_task(tmp_path, monkeypatch):
    task_file = tmp_path / "active-task.json"
    monkeypatch.setattr("hui_mcp.active_task_store.ACTIVE_TASK", task_file)
    task_file.write_text(
        json.dumps({"task_id": "abc123", "text": "hello"}),
        encoding="utf-8",
    )
    assert read_active_task() == {"task_id": "abc123", "text": "hello"}


def test_read_active_task_skips_voice_channel(tmp_path, monkeypatch):
    task_file = tmp_path / "active-task.json"
    monkeypatch.setattr("hui_mcp.active_task_store.ACTIVE_TASK", task_file)
    task_file.write_text(
        json.dumps({"task_id": "v1", "text": "hi", "channel": "voice"}),
        encoding="utf-8",
    )
    assert read_active_task() is None


def test_read_active_voice(tmp_path, monkeypatch):
    voice_file = tmp_path / "active-voice.json"
    monkeypatch.setattr("hui_mcp.active_task_store.ACTIVE_VOICE", voice_file)
    voice_file.write_text(
        json.dumps(
            {
                "utterance_id": "u123",
                "session_id": "s1",
                "text": "你好",
                "channel": "voice",
            }
        ),
        encoding="utf-8",
    )
    assert read_active_voice() == {
        "utterance_id": "u123",
        "text": "你好",
        "session_id": "s1",
    }


def test_clear_task_artifacts(tmp_path, monkeypatch):
    task_file = tmp_path / "active-task.json"
    voice_file = tmp_path / "active-voice.json"
    monkeypatch.setattr("hui_mcp.active_task_store.ACTIVE_TASK", task_file)
    monkeypatch.setattr("hui_mcp.active_task_store.ACTIVE_VOICE", voice_file)
    task_file.write_text(
        json.dumps({"task_id": "abc123", "text": "hello", "channel": "text"}),
        encoding="utf-8",
    )
    voice_file.write_text(
        json.dumps({"utterance_id": "abc123", "text": "hello", "channel": "voice"}),
        encoding="utf-8",
    )
    clear_task_artifacts("abc123")
    assert not task_file.exists()
    assert not voice_file.exists()


def test_read_active_task_missing():
    assert read_active_task() is None or isinstance(read_active_task(), dict)
