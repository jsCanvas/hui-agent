"""Scroll-read a document section and build a text summary."""

from __future__ import annotations

import hashlib
import platform
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from hui_mcp.agent.reading_workflow import (
    SCROLL_ADVANCE_DY,
    SCROLL_NUDGE_DY,
    document_focus_point,
)
from hui_mcp.input.focus import activate_document_app
from hui_mcp.ocr.extract import ocr_available, ocr_image

ToolFn = Callable[[str, dict | None], dict]
ProgressFn = Callable[[str, str], None]
CancelFn = Callable[[], bool]

_SECTION_RE = re.compile(r"第([一二三四五六七八九十百零\d]+)节")
_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _cn_section_num(label: str) -> int | None:
    if label.isdigit():
        return int(label)
    if label in _CN_DIGITS:
        return _CN_DIGITS[label]
    if label.startswith("十") and len(label) == 2 and label[1] in _CN_DIGITS:
        return 10 + _CN_DIGITS[label[1]]
    if len(label) == 2 and label[0] in _CN_DIGITS and label[1] == "十":
        return _CN_DIGITS[label[0]] * 10
    return None


def next_section_marker(section_query: str) -> str | None:
    m = _SECTION_RE.search(section_query)
    if not m:
        return None
    n = _cn_section_num(m.group(1))
    if n is None or n >= 20:
        return None
    nxt = n + 1
    inv = {v: k for k, v in _CN_DIGITS.items() if v <= 10}
    label = inv.get(nxt, str(nxt))
    return f"第{label}节"


def _file_hash(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.md5(p.read_bytes()).hexdigest()


def _result_path(outcome: dict, key: str = "path") -> str | None:
    if not outcome.get("ok"):
        return None
    result = outcome.get("result")
    if isinstance(result, dict):
        return result.get(key) or result.get("directory")
    return None


def _content_hash(path: str | None) -> str | None:
    """Hash document region only, ignoring Companion UI updates on the right/bottom."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(p) as im:
            w, h = im.size
            box = (0, 0, int(w * 0.72), int(h * 0.82))
            crop = im.crop(box).convert("L").resize((max(1, w // 8), max(1, h // 8)))
            return hashlib.md5(crop.tobytes()).hexdigest()
    except Exception:
        return _file_hash(path)


def _click_doc(tool: ToolFn, x: int, y: int) -> None:
    tool("mouse_click", {"x": x, "y": y, "button": "left"})


def _paste_text(tool: ToolFn, text: str) -> tuple[bool, str | None]:
    """Paste text via clipboard (required for Chinese; cliclick cannot type CJK)."""
    mod = "cmd" if platform.system() == "Darwin" else "ctrl"
    if platform.system() == "Darwin":
        try:
            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
                timeout=3,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            return False, f"写入剪贴板失败：{e}"
        out = tool("keyboard_hotkey", {"keys": [mod, "v"]})
    else:
        out = tool("keyboard_type", {"text": text})
    if not out.get("ok"):
        return False, f"粘贴失败：{out.get('error')}"
    return True, None


def search_section(
    tool: ToolFn,
    query: str,
    progress: ProgressFn,
    *,
    keep_foreground: bool = False,
    cancel_check: CancelFn | None = None,
) -> tuple[bool, str | None]:
    if cancel_check and cancel_check():
        return False, "用户按 Esc 终止"

    if keep_foreground:
        progress("focus", "保持当前文档页，准备搜索…")
    else:
        progress("focus", "切换到文档窗口…")
        activate_document_app()
    info = tool("get_screen_info", {})
    w, h = 1440, 900
    if info.get("ok") and info.get("result"):
        w = int(info["result"].get("width", w))
        h = int(info["result"].get("height", h))
    cx, cy = document_focus_point(w, h)
    _click_doc(tool, cx, cy)
    time.sleep(0.15)

    progress("screenshot", "获取当前屏幕画面…")
    shot = tool("get_screenshot", {})
    if not shot.get("ok"):
        return False, f"截屏失败：{shot.get('error')}"

    progress("search", f"在页面中搜索「{query}」…")
    if cancel_check and cancel_check():
        return False, "用户按 Esc 终止"
    mod = "cmd" if platform.system() == "Darwin" else "ctrl"
    out = tool("keyboard_hotkey", {"keys": [mod, "f"]})
    if not out.get("ok"):
        return False, f"打开查找框失败：{out.get('error')}"
    time.sleep(0.2)
    tool("keyboard_hotkey", {"keys": [mod, "a"]})
    time.sleep(0.08)
    ok, err = _paste_text(tool, query)
    if not ok:
        return False, err
    out = tool("keyboard_press", {"key": "enter"})
    if not out.get("ok"):
        return False, f"搜索确认失败：{out.get('error')}"
    time.sleep(0.45)
    return True, None


def dismiss_search_and_focus(
    tool: ToolFn,
    progress: ProgressFn,
    *,
    keep_foreground: bool = False,
) -> tuple[int, int]:
    """Close find UI, focus scrollable document; return scroll anchor point."""
    progress("focus", "关闭查找框并聚焦页面…")
    if not keep_foreground:
        activate_document_app()
    info = tool("get_screen_info", {})
    w, h = 1440, 900
    if info.get("ok") and info.get("result"):
        w = int(info["result"].get("width", w))
        h = int(info["result"].get("height", h))
    cx, cy = document_focus_point(w, h)

    _click_doc(tool, cx, cy)
    time.sleep(0.12)
    mod = "cmd" if platform.system() == "Darwin" else "ctrl"
    tool("keyboard_hotkey", {"keys": [mod, "f"]})
    time.sleep(0.12)
    tool("keyboard_press", {"key": "esc"})
    time.sleep(0.1)
    _click_doc(tool, cx, cy)
    time.sleep(0.15)
    return cx, cy


def _scroll_wheel(tool: ToolFn, cx: int, cy: int, dy: int) -> None:
    if not dy:
        return
    _click_doc(tool, cx, cy)
    time.sleep(0.08)
    tool("mouse_scroll", {"dy": dy, "x": cx, "y": cy})
    time.sleep(0.12)


def _center_reading_viewport(tool: ToolFn, cx: int, cy: int) -> None:
    """After find-in-page, nudge content toward vertical center (small steps)."""
    _click_doc(tool, cx, cy)
    time.sleep(0.08)
    for _ in range(2):
        tool("mouse_scroll", {"dy": -SCROLL_NUDGE_DY, "x": cx, "y": cy})
        time.sleep(0.1)


def _scroll_document(
    tool: ToolFn,
    cx: int,
    cy: int,
    *,
    page_downs: int = 0,
    scroll_dy: int = SCROLL_ADVANCE_DY,
) -> None:
    """Advance reading by ~35% viewport — incremental wheel only, no Page Down."""
    _scroll_wheel(tool, cx, cy, scroll_dy)
    for _ in range(page_downs):
        tool("keyboard_press", {"key": "page-down"})
        time.sleep(0.12)


def _dedupe_pages(pages: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for path in pages:
        h = _content_hash(path) or _file_hash(path)
        if h and h in seen:
            continue
        if h:
            seen.add(h)
        unique.append(path)
    return unique


def scroll_capture_pages(
    tool: ToolFn,
    progress: ProgressFn,
    *,
    section_query: str,
    max_pages: int = 24,
    page_downs: int = 0,
    scroll_dy: int = SCROLL_ADVANCE_DY,
    stale_hits_to_stop: int = 2,
    keep_foreground: bool = False,
    cancel_check: CancelFn | None = None,
) -> list[str]:
    """Scroll document; capture screenshots until bottom or next section."""
    if cancel_check and cancel_check():
        progress("cancel", "用户按 Esc 终止")
        return []

    cx, cy = dismiss_search_and_focus(tool, progress, keep_foreground=keep_foreground)
    _center_reading_viewport(tool, cx, cy)

    pages: list[str] = []
    stop_marker = next_section_marker(section_query)
    prev_hash: str | None = None
    stale_hits = 0

    if not keep_foreground:
        activate_document_app()
    shot0 = tool("get_screenshot", {})
    path0 = _result_path(shot0)
    if path0:
        pages.append(path0)
        prev_hash = _content_hash(path0)

    for page in range(max_pages):
        if cancel_check and cancel_check():
            progress("cancel", "用户按 Esc 终止，停止滚动")
            break
        progress("scroll", f"向下滚动阅读（第 {page + 1}/{max_pages} 屏）…")
        if not keep_foreground:
            activate_document_app()
        _scroll_document(tool, cx, cy, page_downs=page_downs, scroll_dy=scroll_dy)
        time.sleep(0.25)
        if not keep_foreground:
            activate_document_app()
        time.sleep(0.12)

        shot = tool("get_screenshot", {})
        path = _result_path(shot)
        if not path:
            break

        h = _content_hash(path)
        if h and h == prev_hash:
            stale_hits += 1
            if stale_hits >= stale_hits_to_stop:
                progress("scroll", "检测到页面已到底（截图去重），停止滚动")
                break
        else:
            stale_hits = 0
        prev_hash = h
        pages.append(path)

        if stop_marker and ocr_available():
            text = ocr_image(path)
            if text and stop_marker in text and len(pages) > 1:
                progress("scroll", f"检测到「{stop_marker}」，本节阅读完成")
                break

        time.sleep(0.15)

    return _dedupe_pages(pages)


def build_summary(section_query: str, page_paths: list[str]) -> tuple[str, str, list[str]]:
    """Return (summary_reply, full_ocr_text, per_page_snippets)."""
    snippets: list[str] = []
    for path in page_paths:
        text = ocr_image(path)
        if text:
            snippets.append(text)

    if snippets:
        lines: list[str] = []
        seen: set[str] = set()
        for block in snippets:
            for line in block.splitlines():
                line = line.strip()
                if len(line) < 2 or line in seen:
                    continue
                seen.add(line)
                lines.append(line)
        full_text = "\n".join(lines)
        preview = full_text[:2800]
        if len(full_text) > 2800:
            preview += "\n\n…（OCR 全文见 data.ocr_text）"
        summary = (
            f"【{section_query} 阅读摘要】\n"
            f"共滚动采集 {len(page_paths)} 屏，OCR 提取 {len(full_text)} 字。\n\n"
            f"{preview}"
        )
        return summary, full_text, snippets

    paths_block = "\n".join(f"- {p}" for p in page_paths[:8])
    if len(page_paths) > 8:
        paths_block += f"\n- …共 {len(page_paths)} 张"
    hint = (
        "未安装 tesseract，无法 OCR 总结。"
        if not ocr_available()
        else "未能从截图识别文字（请确认浏览器文档区域可见）。"
    )
    summary = (
        f"【{section_query} 滚动阅读完成】\n"
        f"共采集 {len(page_paths)} 屏截图。\n"
        f"{hint}\n\n"
        f"截图路径：\n{paths_block}\n\n"
        "安装 OCR：brew install tesseract tesseract-lang\n"
        "或通过 Socket 将截图交给 VLM 做总结。"
    )
    return summary, "", snippets
