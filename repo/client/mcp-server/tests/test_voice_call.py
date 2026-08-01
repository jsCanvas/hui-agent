"""Voice call session tests."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.voice.call_session import VoiceCallSession, reset_session


def test_process_utterance_runs_agent_and_speaks():
    reset_session()
    ctx = AppContext(config=AppConfig.load())
    runtime = AgentRuntime(ctx)
    session = VoiceCallSession(ctx, runtime)
    events: list[dict] = []
    session.event_sink = events.append

    with patch("hui_mcp.voice.call_session.invoke_tool") as mock_tool:
        mock_tool.side_effect = [
            {"ok": True, "result": {"engine": "edge-tts", "duration_ms": 100}},
        ]
        with patch.object(runtime, "run") as mock_run:
            from hui_mcp.agent.runtime import AgentResult

            mock_run.return_value = AgentResult("t1", True, "好的，已完成。", [])
            result = session.process_utterance("帮助", speak=True)

    assert result.ok is True
    assert any(e.get("type") == "voice.stt.final" for e in events)
    assert any(e.get("type") == "chat.delta" for e in events)
    assert mock_tool.call_count == 1
    assert mock_tool.call_args[0][1] == "tts_speak"


def test_stt_web_engine_returns_hint():
    from hui_mcp.voice import stt

    result = stt.listen_once(AppConfig.load().stt)
    assert result.ok is False
    assert result.error == "STT_WEB_ONLY"
