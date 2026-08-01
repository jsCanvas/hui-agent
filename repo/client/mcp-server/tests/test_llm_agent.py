"""LLM Agent tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hui_mcp.agent.llm_agent import LlmAgent
from hui_mcp.config import AppConfig, LlmConfig


def test_llm_agent_no_api_key():
    cfg = AppConfig.load()
    cfg.llm = LlmConfig(api_key="")
    cfg.agent.mode = "llm"
    agent = LlmAgent(cfg)
    result = agent.run("截屏", lambda n, a: {"ok": True})
    assert result.ok is False
    assert "API Key" in result.reply


@patch("hui_mcp.agent.llm_agent.LlmClient.chat")
def test_llm_agent_direct_reply(mock_chat):
    mock_chat.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "摘要：第三节讲的是接口规范。"}}]
    }
    cfg = AppConfig.load()
    cfg.llm = LlmConfig(api_key="test-key", model="gpt-4o-mini")
    cfg.agent.mode = "llm"
    tool = MagicMock(return_value={"ok": True, "result": {}})
    result = LlmAgent(cfg).run("总结文档", tool)
    assert result.ok is True
    assert "摘要" in result.reply
    tool.assert_not_called()


@patch("hui_mcp.agent.llm_agent.LlmClient.chat")
def test_llm_agent_tool_then_reply(mock_chat):
    mock_chat.side_effect = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "get_screenshot",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {"message": {"role": "assistant", "content": "已看到浏览器文档，第四节摘要如下…"}}
            ]
        },
    ]
    cfg = AppConfig.load()
    cfg.llm = LlmConfig(api_key="test-key")
    cfg.agent.mode = "llm"

    def fake_tool(name, args):
        return {"ok": True, "result": {"path": "/tmp/fake.png"}}

    with patch("hui_mcp.agent.llm_agent.image_to_data_url", return_value=None):
        result = LlmAgent(cfg).run("阅读第四节", fake_tool)
    assert result.ok is True
    assert "摘要" in result.reply
    assert mock_chat.call_count == 2
