"""Build Cursor follow-up messages for Companion pending tasks."""

from __future__ import annotations

import json
import sys
from typing import Any

from hui_mcp.agent.doc_read_worker import is_doc_read_task
from hui_mcp.agent.reading_workflow import PLANNING_PREAMBLE, SCROLL_POLICY
from hui_mcp.config import AppConfig
from hui_mcp.daemon_client import get_pending


def build_doc_read_followup_agent(task_id: str, text: str, *, allow_activate_document: bool) -> str:
    """Cursor Agent reads the screen via MCP tools (no background OCR Worker)."""
    focus_step = (
        "2) activate_document_app 切换到文档窗口（飞书/浏览器/编辑器）；"
        "get_screen_info；mouse_move + mouse_click 点击文档区聚焦（约屏宽 32%、高 42%）；"
        if allow_activate_document
        else "2) get_screen_info；mouse_move + mouse_click 点击文档区聚焦（约屏宽 32%、高 42%）；"
        "禁止 activate_document_app / activate_cursor_app / cmd+tab。"
    )
    return (
        f"Companion 文档阅读 task_id={task_id}：{text}。"
        "由 Cursor Agent 主动读屏（禁止后台 OCR Worker；"
        "禁止 companion_doc_read_start；禁止轮询 companion_doc_read_status）。"
        f"{PLANNING_PREAMBLE}"
        "请严格按序："
        "1) companion_task_pending 确认 task_id；"
        f"{focus_step}"
        "3) 定位：有章节号则 keyboard_hotkey cmd+f → 粘贴关键词 → enter → Esc 关查找；"
        "定位后 get_screenshot，按段落位置微调滚屏使待读段落在屏幕中央；"
        "全文/文件则直接阅读；"
        f"4) 循环：get_screenshot → Read 截图理解；{SCROLL_POLICY}"
        "5) 按「播报序列」用 companion_speak 分段朗读（每段单独调用，final 在最后）；"
        "6) 综合各屏写中文摘要；"
        "7) companion_task_complete（默认 auto_wait 自动 companion_socket_wait）；"
        "8) 若 task_received 继续处理；若 continue_waiting 再 companion_socket_wait（禁止 companion_socket_disconnect）。"
        "若必须切换窗口，仅用 mouse_move + mouse_click。"
    )


def build_doc_read_followup_foreground(task_id: str, text: str) -> str:
    """Doc read while user stays on document; Agent drives screenshot + input tools."""
    return build_doc_read_followup_agent(task_id, text, allow_activate_document=False)


def build_doc_read_followup_commander(task_id: str, text: str) -> str:
    """Legacy name: still Agent-driven; may activate document first."""
    return build_doc_read_followup_agent(task_id, text, allow_activate_document=True)


def build_doc_read_followup(task_id: str, text: str) -> str:
    cfg = AppConfig.load().doc_read
    if cfg.assume_doc_foreground or cfg.cursor_trigger in (
        "notify",
        "background",
        "notify_only",
    ):
        return build_doc_read_followup_foreground(task_id, text)
    return build_doc_read_followup_commander(task_id, text)


def _duplex_context_block(duplex: dict[str, Any] | None) -> str:
    if not duplex:
        return ""
    ack = duplex.get("ack_text") or ""
    segs = duplex.get("speak_segments") or []
    actions = duplex.get("executed_actions") or duplex.get("simple_actions") or []
    return (
        "【双工·边缘已响应】"
        f"即时回复：{ack}；"
        f"边缘播报序列（勿重复 ack）：{segs}；"
        f"已执行简单动作：{actions}。"
        "请 Cursor 规划完整操作序列与后续播报序列并接管执行。"
    )


def build_voice_followup(utterance_id: str, text: str, duplex: dict[str, Any] | None = None) -> str:
    duplex_block = _duplex_context_block(duplex)
    return (
        f"Companion 通话 utterance_id={utterance_id}：{text}。"
        "你是大脑（Cursor Agent），Companion 经 Socket 双向语音；边缘模型已做即时响应。"
        f"{duplex_block}"
        f"{PLANNING_PREAMBLE}"
        "请：1) companion_task_pending 看 voice_pending 与 duplex 字段 "
        "2) 规划完整操作序列与播报序列（勿重复边缘已播报的 ack）并执行；"
        f"{SCROLL_POLICY}"
        "3) 按播报序列 companion_speak（每段单独调用，final=true 在最后一段）"
        f"4) companion_task_complete channel=voice utterance_id={utterance_id} reply=简短确认（默认 auto_wait 自动监听）；"
        "5) 若 task_received 继续处理；若 continue_waiting 再 companion_socket_wait（禁止 companion_socket_disconnect）。"
        "禁止本地 afplay tts_speak。"
    )


def build_followup_message(
    pending: dict[str, Any] | None,
    voice_pending: dict[str, Any] | None,
) -> str | None:
    if voice_pending:
        uid = voice_pending.get("utterance_id") or ""
        text = voice_pending.get("text") or ""
        if not uid or not text:
            return None
        duplex = voice_pending.get("duplex") if isinstance(voice_pending, dict) else None
        return build_voice_followup(uid, text, duplex)
    if pending:
        task_id = pending.get("task_id") or ""
        text = pending.get("text") or ""
        if not task_id or not text:
            return None
        is_doc, _section = is_doc_read_task(text)
        if is_doc:
            return build_doc_read_followup(task_id, text)
        return (
            f"Companion 有待处理任务 task_id={task_id}：{text}。"
            f"{PLANNING_PREAMBLE}"
            "请：1) companion_task_pending "
            "2) 按操作序列执行（读屏/键鼠按需）；"
            f"{SCROLL_POLICY}"
            "3) companion_task_complete reply=结果（默认 auto_wait 自动监听）；"
            "4) 若 task_received 继续处理；若 continue_waiting 再 companion_socket_wait（禁止 companion_socket_disconnect）。"
        )
    return None


def build_stop_hook_json(data: dict[str, Any] | None = None) -> dict | None:
    if data is None:
        data = get_pending()
    if not data.get("ok"):
        return None
    msg = build_followup_message(data.get("pending"), data.get("voice_pending"))
    if not msg:
        return None
    return {"followup_message": msg}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build Cursor follow-up for Companion tasks")
    parser.add_argument("--task-id", default="", help="Pending task id (skip daemon lookup)")
    parser.add_argument("--text", default="", help="Pending task text (skip daemon lookup)")
    args = parser.parse_args(argv)

    if args.task_id.strip() and args.text.strip():
        msg = build_followup_message(
            {"task_id": args.task_id.strip(), "text": args.text.strip()},
            None,
        )
        payload = {"followup_message": msg} if msg else None
    else:
        payload = build_stop_hook_json()
    if payload:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
