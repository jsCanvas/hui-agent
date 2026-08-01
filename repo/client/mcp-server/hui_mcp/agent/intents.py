"""Rule-based intent classification for Agent Runtime (v0.3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class IntentKind(str, Enum):
    READ_DOC_SECTION = "read_doc_section"
    READ_DOC_SECTION_FULL = "read_doc_section_full"
    SCROLL_DOWN = "scroll_down"
    SCROLL_UP = "scroll_up"
    SCREENSHOT = "screenshot"
    CHECK_PERMISSIONS = "check_permissions"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    kind: IntentKind
    section_query: str | None = None
    scroll_amount: int = 5


_SECTION_RE = re.compile(r"第([一二三四五六七八九十百零\d]+)节")


def classify(text: str) -> Intent:
    t = text.strip().lower()
    if not t:
        return Intent(IntentKind.UNKNOWN)

    if any(k in text for k in ("权限", "permission", "check_permissions")):
        return Intent(IntentKind.CHECK_PERMISSIONS)

    if any(k in text for k in ("帮助", "能做什么", "怎么用", "help")):
        return Intent(IntentKind.HELP)

    if any(k in text for k in ("截图", "截屏", "screenshot", "看一下屏幕", "当前画面")):
        return Intent(IntentKind.SCREENSHOT)

    full_read_keys = ("完整", "总结", "归纳", "全文", "自动滚动", "滚动阅读", "完整阅读")
    if _SECTION_RE.search(text) and any(k in text for k in full_read_keys):
        m = _SECTION_RE.search(text)
        return Intent(
            IntentKind.READ_DOC_SECTION_FULL,
            section_query=m.group(0) if m else "第三节",
        )

    if any(k in text for k in ("阅读", "查看", "定位", "找到", "打开")) and _SECTION_RE.search(text):
        m = _SECTION_RE.search(text)
        query = m.group(0) if m else "第三节"
        return Intent(IntentKind.READ_DOC_SECTION, section_query=query)

    if _SECTION_RE.search(text) and any(k in text for k in ("节", "章节", "文档", "浏览器", "网页")):
        m = _SECTION_RE.search(text)
        return Intent(IntentKind.READ_DOC_SECTION, section_query=m.group(0) if m else "第三节")

    if any(k in text for k in ("向上", "上滚", "scroll up")):
        return Intent(IntentKind.SCROLL_UP, scroll_amount=5)
    if any(k in text for k in ("向下", "滚动", "翻页", "scroll", "滑")):
        return Intent(IntentKind.SCROLL_DOWN, scroll_amount=5)

    if "阅读" in text or "第三节" in text:
        m = _SECTION_RE.search(text)
        return Intent(
            IntentKind.READ_DOC_SECTION,
            section_query=m.group(0) if m else "第三节",
        )

    return Intent(IntentKind.UNKNOWN)
