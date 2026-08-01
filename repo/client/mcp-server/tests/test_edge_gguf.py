"""Tests for GGUF edge model integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from hui_mcp.agent.edge_gguf import default_gguf_path, gguf_model_ready, gguf_runtime_available
from hui_mcp.agent.edge_model import build_outline, edge_outline_status
from hui_mcp.config import AppConfig, DocReadConfig


def test_default_gguf_path():
    p = default_gguf_path()
    assert p.name.endswith(".gguf")
    assert "models" in str(p)


_OCR_SAMPLE = "第四节 正向发货的运费计算\n3.1 卖家端拆包\n- 卖家在订单发货页选择包裹\n- 调用极兔 API 获取面单\n运费按重量计费"


def test_build_outline_builtin_mode():
    cfg = AppConfig()
    cfg.doc_read.edge_model = "builtin"
    outline, used = build_outline("第四节", _OCR_SAMPLE, cfg)
    assert used == "builtin"
    assert "第四节" in outline


@patch("hui_mcp.agent.edge_gguf.gguf_model_ready", return_value=False)
def test_build_outline_auto_fallback(_mock_ready):
    cfg = AppConfig()
    cfg.doc_read.edge_model = "auto"
    outline, used = build_outline("第四节", _OCR_SAMPLE, cfg)
    assert used == "builtin"
    assert outline


@patch("hui_mcp.agent.edge_gguf.build_gguf_outline", return_value="## GGUF 大纲\n- 要点")
@patch("hui_mcp.agent.edge_gguf.gguf_model_ready", return_value=True)
def test_build_outline_uses_gguf(_mock_ready, _mock_gguf):
    cfg = AppConfig()
    cfg.doc_read.edge_model = "auto"
    outline, used = build_outline("第四节", "第四节 " + "内容" * 20, cfg)
    assert used == "gguf"
    assert "GGUF" in outline


def test_edge_outline_status():
    cfg = AppConfig()
    cfg.doc_read.edge_model = "auto"
    st = edge_outline_status(cfg)
    assert st["edge_model"] == "auto"
    assert st["builtin_ready"] is True
    assert "gguf_ready" in st


def test_gguf_model_ready_without_file():
    cfg = DocReadConfig(gguf_model_path="/tmp/nonexistent-hui-agent.gguf")
    assert gguf_model_ready(cfg) is False


def test_gguf_model_ready_with_file(tmp_path: Path):
    model = tmp_path / "test.gguf"
    model.write_bytes(b"GGUF" + b"x" * 2_000_000)
    cfg = DocReadConfig(gguf_model_path=str(model))
    with patch("hui_mcp.agent.edge_gguf.gguf_runtime_available", return_value=True):
        assert gguf_model_ready(cfg) is False  # too small vs MIN_GGUF_BYTES
    model.write_bytes(b"GGUF" + b"x" * 460_000_000)
    with patch("hui_mcp.agent.edge_gguf.gguf_runtime_available", return_value=True):
        assert gguf_model_ready(cfg) is True
