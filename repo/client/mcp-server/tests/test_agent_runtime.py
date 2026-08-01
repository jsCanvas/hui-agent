"""Agent Runtime tests."""

from __future__ import annotations

from unittest.mock import patch

from hui_mcp.agent.intents import IntentKind, classify
from hui_mcp.agent.runtime import AgentRuntime
from hui_mcp.context import AppContext


def test_classify_read_section():
    intent = classify("阅读桌面浏览器网页上的需求文档第三节")
    assert intent.kind == IntentKind.READ_DOC_SECTION
    assert intent.section_query == "第三节"


def test_classify_read_section_full():
    intent = classify("完整阅读物流服务文档第四节并总结")
    assert intent.kind == IntentKind.READ_DOC_SECTION_FULL
    assert intent.section_query == "第四节"


def test_next_section_marker():
    from hui_mcp.agent.read_section_flow import next_section_marker

    assert next_section_marker("第四节") == "第五节"
    assert next_section_marker("第三节") == "第四节"


def test_classify_help():
    assert classify("帮助").kind == IntentKind.HELP


def test_classify_scroll():
    assert classify("向下滚动页面").kind == IntentKind.SCROLL_DOWN


@patch("hui_mcp.cursor_relay.get_relay")
def test_cursor_relay_mode(mock_get_relay):
    relay = mock_get_relay.return_value
    relay.run_task.return_value = {
        "ok": True,
        "reply": "第四节摘要：运费计算…",
        "steps": [{"step": "done", "message": "ok"}],
        "task_id": "t1",
        "data": None,
    }
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    ctx.config.agent.mode = "cursor"
    result = AgentRuntime(ctx).run("完整阅读第四节并总结")
    assert result.ok is True
    assert "摘要" in result.reply
    relay.run_task.assert_called_once()


@patch("hui_mcp.cursor_relay.get_relay")
def test_cursor_mode_offline(mock_get_relay):
    relay = mock_get_relay.return_value
    relay.run_task.return_value = {
        "ok": False,
        "reply": "Cursor 未通过 Socket 连接。",
        "steps": [],
        "task_id": "t2",
    }
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    ctx.config.agent.mode = "cursor"
    result = AgentRuntime(ctx).run("完整阅读第四节并总结")
    assert result.ok is False
    assert "Socket" in result.reply


@patch("hui_mcp.agent.read_section_flow.activate_document_app", return_value="Safari")
@patch("hui_mcp.agent.runtime.invoke_tool")
def test_read_section_orchestration(mock_invoke, _mock_activate):
    mock_invoke.side_effect = [
        {"ok": True, "result": {"path": "/tmp/before.png"}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {"width": 1440, "height": 900}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {"path": "/tmp/after.png"}},
        {"ok": True, "result": {"directory": "/tmp/frames", "manifest": {}}},
    ]
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    ctx.config.agent.mode = "rules"
    runtime = AgentRuntime(ctx)
    steps_log = []

    def on_progress(task_id, step, msg):
        steps_log.append((step, msg))

    result = runtime.run("阅读浏览器第三节", on_progress)
    assert result.ok is True
    assert "第三节" in result.reply
    assert any(s.step == "search" for s in result.steps)
    assert mock_invoke.call_count >= 5
    assert len(steps_log) >= 3


@patch("hui_mcp.agent.runtime.invoke_tool")
def test_help_no_tools(mock_invoke):
    ctx = AppContext(config=__import__("hui_mcp.config", fromlist=["AppConfig"]).AppConfig.load())
    ctx.config.agent.mode = "rules"
    result = AgentRuntime(ctx).run("帮助")
    assert result.ok is True
    assert "向下滚动" in result.reply
    mock_invoke.assert_not_called()
