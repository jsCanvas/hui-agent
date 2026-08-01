"""Duplex voice architecture — edge instant ack + simple actions; Cursor plans full execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hui_mcp.agent.intents import IntentKind, classify
from hui_mcp.agent.reading_workflow import document_focus_point
from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.tools.registry import invoke_tool

log = logging.getLogger("hui_mcp.voice.duplex")

_READ_KEYS = ("阅读", "朗读", "读一下", "读屏", "总结", "归纳", "小说", "文档", "章节", "小节")


@dataclass
class SimpleAction:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "label": self.label or self.tool,
        }


@dataclass
class DuplexPlan:
    ack_text: str
    speak_segments: list[str]
    simple_actions: list[SimpleAction]
    defer_to_cursor: bool
    intent: str
    edge_tier: str = "builtin"
    executed_actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ack_text": self.ack_text,
            "speak_segments": self.speak_segments,
            "simple_actions": [a.to_dict() for a in self.simple_actions],
            "executed_actions": self.executed_actions,
            "defer_to_cursor": self.defer_to_cursor,
            "intent": self.intent,
            "edge_tier": self.edge_tier,
        }


def _needs_cursor(text: str, intent_kind: IntentKind) -> bool:
    if intent_kind in (
        IntentKind.READ_DOC_SECTION,
        IntentKind.READ_DOC_SECTION_FULL,
        IntentKind.UNKNOWN,
    ):
        return True
    if any(k in text for k in _READ_KEYS):
        return True
    return False


def _ack_for_read(text: str, intent) -> str:
    section = getattr(intent, "section_query", None) or ""
    if section:
        return f"好的，我来{section}相关内容，请稍等。"
    if "小说" in text:
        return "好的，我来用中文阅读，请稍等。"
    if "总结" in text or "归纳" in text:
        return "好的，我先看一下内容，再为你总结。"
    return "好的，收到，我先读屏看一下。"


def build_duplex_plan(text: str, cfg: AppConfig) -> DuplexPlan:
    """Build instant ack, speak list, and simple action table for duplex mode."""
    text = (text or "").strip()
    intent = classify(text)
    tier = (cfg.voice.edge_tier or "builtin").lower()

    if intent.kind == IntentKind.HELP:
        segs = [
            "我是小绘，可以帮你阅读文档、滚屏和截屏。",
            "你可以说：阅读某一节、向下滚动、或截屏。",
        ]
        return DuplexPlan(
            ack_text=segs[0],
            speak_segments=segs,
            simple_actions=[],
            defer_to_cursor=False,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    if intent.kind == IntentKind.CHECK_PERMISSIONS:
        return DuplexPlan(
            ack_text="好的，我来检查权限状态。",
            speak_segments=["好的，我来检查权限状态。"],
            simple_actions=[SimpleAction("check_permissions", {}, "检查权限")],
            defer_to_cursor=False,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    if intent.kind == IntentKind.SCREENSHOT:
        return DuplexPlan(
            ack_text="好的，正在截屏。",
            speak_segments=["好的，正在截屏。"],
            simple_actions=[SimpleAction("get_screenshot", {}, "截屏")],
            defer_to_cursor=False,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    if intent.kind == IntentKind.SCROLL_DOWN:
        return DuplexPlan(
            ack_text="好的，我来向下滚动一点。",
            speak_segments=["好的，我来向下滚动一点。"],
            simple_actions=[
                SimpleAction("get_screen_info", {}, "读屏尺寸"),
                SimpleAction("mouse_scroll", {"dy": -24}, "向下滚动"),
            ],
            defer_to_cursor=False,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    if intent.kind == IntentKind.SCROLL_UP:
        return DuplexPlan(
            ack_text="好的，我来向上滚动一点。",
            speak_segments=["好的，我来向上滚动一点。"],
            simple_actions=[
                SimpleAction("get_screen_info", {}, "读屏尺寸"),
                SimpleAction("mouse_scroll", {"dy": 24}, "向上滚动"),
            ],
            defer_to_cursor=False,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    if _needs_cursor(text, intent.kind):
        ack = _ack_for_read(text, intent)
        segs = [ack]
        if cfg.voice.followup_speak:
            segs.append("我正在读屏分析，完整内容稍后继续播报。")
        actions = [
            SimpleAction("get_screen_info", {}, "读屏尺寸"),
        ]
        if cfg.doc_read.assume_doc_foreground:
            actions.insert(0, SimpleAction("get_screenshot", {}, "首帧读屏"))
        else:
            actions.insert(0, SimpleAction("activate_document_app", {}, "激活文档"))
        return DuplexPlan(
            ack_text=ack,
            speak_segments=segs,
            simple_actions=actions,
            defer_to_cursor=True,
            intent=intent.kind.value,
            edge_tier=tier,
        )

    return DuplexPlan(
        ack_text="好的，收到。",
        speak_segments=["好的，收到。"],
        simple_actions=[],
        defer_to_cursor=True,
        intent=intent.kind.value,
        edge_tier=tier,
    )


def _maybe_enrich_with_gguf(plan: DuplexPlan, text: str, cfg: AppConfig) -> DuplexPlan:
    if (cfg.voice.edge_tier or "").lower() != "gguf":
        return plan
    try:
        from hui_mcp.agent.edge_gguf import plan_voice_duplex_gguf

        enriched = plan_voice_duplex_gguf(text, cfg.doc_read)
        if not enriched:
            return plan
        plan.ack_text = enriched.get("ack_text") or plan.ack_text
        segs = enriched.get("speak_segments")
        if isinstance(segs, list) and segs:
            plan.speak_segments = [str(s).strip() for s in segs if str(s).strip()]
        plan.edge_tier = "gguf"
    except Exception as e:
        log.debug("gguf duplex enrich skipped: %s", e)
    return plan


def execute_simple_actions(ctx: AppContext, actions: list[SimpleAction]) -> list[dict[str, Any]]:
    """Run edge simple action table (mouse/keyboard/screenshot)."""
    executed: list[dict[str, Any]] = []
    screen: dict[str, Any] | None = None

    for action in actions:
        args = dict(action.arguments)
        if action.tool == "mouse_scroll" and ("x" not in args or "y" not in args):
            if screen is None:
                info_out = invoke_tool(ctx, "get_screen_info", {})
                screen = info_out.get("result") if info_out.get("ok") else {}
            w = int((screen or {}).get("width") or 1440)
            h = int((screen or {}).get("height") or 900)
            cx, cy = document_focus_point(w, h)
            args.setdefault("x", cx)
            args.setdefault("y", cy)

        try:
            out = invoke_tool(ctx, action.tool, args)
            executed.append(
                {
                    "tool": action.tool,
                    "label": action.label,
                    "ok": bool(out.get("ok")),
                    "result": out.get("result"),
                    "error": out.get("error"),
                }
            )
            if action.tool == "get_screen_info" and out.get("ok"):
                screen = out.get("result")
        except Exception as e:
            log.warning("duplex action %s failed: %s", action.tool, e)
            executed.append(
                {
                    "tool": action.tool,
                    "label": action.label,
                    "ok": False,
                    "error": str(e),
                }
            )
    return executed


def _unique_segments(plan: DuplexPlan) -> list[str]:
    """De-duplicate speak segments (ack often equals speak_segments[0])."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in plan.speak_segments or ([plan.ack_text] if plan.ack_text else []):
        t = (raw or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _speak_edge_instant(
    relay,
    utterance_id: str,
    plan: DuplexPlan,
    cfg: AppConfig,
) -> None:
    """Instant ack only once; optional follow-up lines exclude ack duplicates."""
    if not cfg.voice.instant_speak:
        return
    segments = _unique_segments(plan)
    if not segments:
        return
    relay.speak(segments[0], utterance_id=utterance_id, wait_playback=False)
    if not cfg.voice.followup_speak or not plan.defer_to_cursor:
        return
    for seg in segments[1:]:
        relay.speak(seg, utterance_id=utterance_id, wait_playback=False)


def handle_voice_duplex(ctx: AppContext, text: str) -> dict[str, Any]:
    """Duplex entry: instant edge response, then defer to Cursor or finish locally."""
    from hui_mcp.voice_relay import get_voice_relay

    cfg = ctx.config
    if not cfg.voice.enabled:
        return get_voice_relay().submit_utterance(text)

    plan = build_duplex_plan(text, cfg)
    plan = _maybe_enrich_with_gguf(plan, text, cfg)
    relay = get_voice_relay()

    if plan.defer_to_cursor:
        outcome = relay.submit_utterance(text, duplex_plan=plan.to_dict())
        if not outcome.get("ok"):
            return outcome
        uid = outcome.get("utterance_id") or ""
        _run_duplex_fast_path(ctx, relay, uid, plan, cfg)
        outcome["duplex"] = plan.to_dict()
        outcome["edge_only"] = False
        return outcome

    uid = relay.begin_local_turn(text, duplex_plan=plan.to_dict())
    if plan.simple_actions and cfg.voice.execute_simple_actions:
        plan.executed_actions = execute_simple_actions(ctx, plan.simple_actions)
        relay.update_duplex_plan(uid, plan.to_dict())
    segments = _unique_segments(plan)
    for i, seg in enumerate(segments):
        relay.speak(
            seg,
            utterance_id=uid,
            final=(i == len(segments) - 1),
            wait_playback=True,
        )
    relay.complete_turn(uid, reply=plan.ack_text, ok=True)
    return {
        "ok": True,
        "utterance_id": uid,
        "edge_only": True,
        "duplex": plan.to_dict(),
    }


def _run_duplex_fast_path(
    ctx: AppContext,
    relay,
    utterance_id: str,
    plan: DuplexPlan,
    cfg: AppConfig,
) -> None:
    if plan.simple_actions and cfg.voice.execute_simple_actions:
        plan.executed_actions = execute_simple_actions(ctx, plan.simple_actions)
        relay.update_duplex_plan(utterance_id, plan.to_dict())

    _speak_edge_instant(relay, utterance_id, plan, cfg)
