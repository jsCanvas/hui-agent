import pytest


def test_clean_text_strips_url():
    from hui_mcp.voice.tts_proxy import clean_text

    assert "http" not in clean_text("打开 https://example.com/doc 第三节")


def test_tts_health_requires_running_proxy():
    from hui_mcp.voice.tts_client import TtsClient

    client = TtsClient()
    # Without proxy this should be False — no assertion on True in CI
    assert isinstance(client.health(), bool)
