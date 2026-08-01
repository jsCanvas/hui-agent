"""Tests for built-in local edge outline model."""

from __future__ import annotations

from hui_mcp.agent.edge_model import build_local_outline, edge_model_available


def test_edge_model_always_available():
    assert edge_model_available() is True


def test_build_local_outline_extracts_structure():
    ocr = """
第四节 正向发货的运费计算
3.1 卖家端拆包
- 卖家在订单发货页选择包裹
- 调用极兔 API 获取面单
POST /api/shipping/label
orderId: 12345
步骤1：拆包裹 然后 步骤2：打印面单
运费按重量计费
"""
    outline = build_local_outline("第四节", ocr)
    assert "第四节" in outline
    assert "要点" in outline or "拆包" in outline or "极兔" in outline
    assert len(outline) > 80


def test_build_local_outline_short_text():
    assert build_local_outline("第四节", "太短") == ""
