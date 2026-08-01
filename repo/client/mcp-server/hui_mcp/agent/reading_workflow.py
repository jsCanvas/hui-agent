"""Shared document-reading scroll policy and agent planning prompts."""

from __future__ import annotations

# Document click / scroll anchor (left-center, away from Companion bottom-right).
DOCUMENT_FOCUS_X_RATIO = 0.32
DOCUMENT_FOCUS_Y_RATIO = 0.42
READING_CENTER_Y_RATIO = 0.42

# Incremental scroll steps — avoid page jumps.
SCROLL_NUDGE_DY = 12
SCROLL_ADVANCE_DY = 24
MAX_SCROLL_DY = 24

PLANNING_PREAMBLE = (
    "0) 先思考（此步不调用工具）：理解任务目标；"
    "列出「操作序列」（聚焦→查找→微调滚屏→读屏循环）与「播报序列」（分段中文口播文本，final 在最后）；"
    "确认后再逐步执行。"
)

SCROLL_POLICY = (
    "滚屏细则（禁止猛滚到底）："
    "文档区焦点 x≈width×0.32、y≈height×0.42；"
    "每轮读前先 get_screenshot，判断待读段落在屏上/中/下："
    "居上则 mouse_scroll dy=-12～-24 下滚，居下则 dy=+12～+24 上滚，已居中则不滚；"
    "目标是让待读段落落在屏幕垂直中央（约 height×0.42）；"
    "禁止 keyboard_press page-down 连按；禁止单次 |dy|>24；"
    "读完当前段落后，下移约一屏 35%（mouse_scroll dy=-24 一次）再读下一段；"
    "连续两屏内容基本相同则停止。"
)


def document_focus_point(width: int, height: int) -> tuple[int, int]:
    return int(width * DOCUMENT_FOCUS_X_RATIO), int(height * DOCUMENT_FOCUS_Y_RATIO)
