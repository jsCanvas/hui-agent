"""STT input mode config."""

from hui_mcp.config import SttConfig


def test_stt_input_mode_default():
    cfg = SttConfig()
    assert cfg.input_mode == "push_to_talk"
