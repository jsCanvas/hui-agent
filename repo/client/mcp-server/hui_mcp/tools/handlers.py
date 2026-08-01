"""MCP tool handlers."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from hui_mcp.context import AppContext
from hui_mcp.ocr.extract import ocr_available
from hui_mcp.voice import manager as voice_manager
from hui_mcp.voice import player as audio_player
from hui_mcp.voice.tts_client import TtsClient


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def handle_get_recent_frames(ctx: AppContext, arguments: dict) -> str:
    ring = ctx.ensure_ring()
    dest = ring.materialize_to_dir()
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    return _json({"directory": str(dest), "manifest": manifest})


def handle_get_screenshot(ctx: AppContext, arguments: dict) -> str:
    png = ctx.grabber.grab_png()
    fd, path = tempfile.mkstemp(suffix=".png", prefix="hui-screenshot-")
    import os

    os.close(fd)
    p = Path(path)
    p.write_bytes(png)
    info = ctx.grabber.monitor_info()
    return _json(
        {
            "path": str(p),
            "width": info.width,
            "height": info.height,
            "scale_factor": info.scale_factor,
            "size_bytes": len(png),
        }
    )


def handle_get_screen_info(ctx: AppContext, arguments: dict) -> str:
    info = ctx.grabber.monitor_info()
    return _json(
        {
            "id": info.id,
            "width": info.width,
            "height": info.height,
            "scale_factor": info.scale_factor,
            "origin": {"x": info.origin_x, "y": info.origin_y},
        }
    )


def handle_activate_document_app(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.input.focus import activate_document_app

    name = activate_document_app()
    return _json({"ok": bool(name), "app": name})


def handle_activate_cursor_app(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.input.focus import activate_cursor_app

    name = activate_cursor_app()
    return _json({"ok": bool(name), "app": name})


def handle_check_permissions(ctx: AppContext, arguments: dict) -> str:
    import platform

    system = platform.system()
    items = []
    if system == "Darwin":
        try:
            png = ctx.grabber.grab_png()
            items.append({"name": "screen_recording", "ok": len(png) > 0})
        except Exception as e:
            items.append({"name": "screen_recording", "ok": False, "hint": str(e)})
        try:
            ctx.ensure_driver().get_position()
            items.append({"name": "accessibility", "ok": True})
        except Exception as e:
            items.append({"name": "accessibility", "ok": False, "hint": str(e)})
    else:
        items.append({"name": "desktop_input", "ok": True})
    tts_ok = TtsClient(ctx.config.tts).health()
    items.append({"name": "edge_tts", "ok": tts_ok, "hint": "start tts proxy or check network"})
    return _json({"platform": system, "permissions": items})


def handle_mouse_get_position(ctx: AppContext, arguments: dict) -> str:
    x, y = ctx.ensure_driver().get_position()
    return _json({"x": x, "y": y})


def handle_mouse_move(ctx: AppContext, arguments: dict) -> str:
    x, y = int(arguments["x"]), int(arguments["y"])
    fast = bool(arguments.get("fast"))
    if fast:
        ctx.ensure_driver().move_instant(x, y)
    else:
        steps = int(arguments["steps"]) if arguments.get("steps") is not None else None
        ctx.ensure_driver().move_smooth(x, y, steps=steps)
    return _json({"ok": True, "x": x, "y": y, "fast": fast})


def handle_mouse_click(ctx: AppContext, arguments: dict) -> str:
    x, y = int(arguments["x"]), int(arguments["y"])
    button = arguments.get("button", "left")
    clicks = int(arguments.get("clicks", 1))
    fast = bool(arguments.get("fast"))
    ctx.ensure_driver().click(x, y, button=button, clicks=clicks, fast=fast)
    return _json({"ok": True, "x": x, "y": y, "button": button, "clicks": clicks, "fast": fast})


def handle_mouse_drag(ctx: AppContext, arguments: dict) -> str:
    ctx.ensure_driver().drag(
        int(arguments["x1"]),
        int(arguments["y1"]),
        int(arguments["x2"]),
        int(arguments["y2"]),
    )
    return _json({"ok": True})


def handle_mouse_scroll(ctx: AppContext, arguments: dict) -> str:
    import time

    from hui_mcp.input.focus import activate_document_app

    dx = int(arguments.get("dx", 0))
    dy = int(arguments.get("dy", 0))
    driver = ctx.ensure_driver()
    x = arguments.get("x")
    y = arguments.get("y")

    if x is not None and y is not None:
        activate_document_app()
        time.sleep(0.08)
        driver.click(int(x), int(y), fast=True)
        time.sleep(0.12)
    elif dy or dx:
        activate_document_app()
        time.sleep(0.05)

    from hui_mcp.agent.reading_workflow import MAX_SCROLL_DY
    from hui_mcp.input.scroll_steps import scroll_incremental

    clamped_dy = max(-MAX_SCROLL_DY, min(MAX_SCROLL_DY, dy)) if dy else 0
    clamped_dx = max(-MAX_SCROLL_DY, min(MAX_SCROLL_DY, dx)) if dx else 0
    scroll_incremental(driver, clamped_dx, clamped_dy)

    return _json(
        {
            "ok": True,
            "dx": clamped_dx,
            "dy": clamped_dy,
            "x": x,
            "y": y,
        }
    )


def handle_keyboard_press(ctx: AppContext, arguments: dict) -> str:
    key = arguments["key"]
    if str(key).lower() in ("esc", "escape"):
        from hui_mcp.task_cancel import get_task_cancel

        if get_task_cancel().is_active():
            get_task_cancel().suppress_esc_cancel()
    ctx.ensure_driver().press_key(key)
    return _json({"ok": True, "key": key})


def handle_keyboard_hotkey(ctx: AppContext, arguments: dict) -> str:
    keys = arguments["keys"]
    ctx.ensure_driver().hotkey(list(keys))
    return _json({"ok": True, "keys": keys})


def handle_keyboard_type(ctx: AppContext, arguments: dict) -> str:
    text = arguments["text"]
    ctx.ensure_driver().type_text(text)
    return _json({"ok": True, "length": len(text)})


def handle_tts_speak(ctx: AppContext, arguments: dict) -> str:
    if ctx.config.tts.auto_start_proxy:
        voice_manager.ensure_proxy(ctx.config)
    client = TtsClient(ctx.config.tts)
    result = client.synthesize(
        arguments["text"],
        voice=arguments.get("voice"),
        rate=arguments.get("rate"),
        pitch=arguments.get("pitch"),
        volume=arguments.get("volume"),
    )
    proc = audio_player.play_mp3(result.audio)
    # Rough duration estimate from mp3 size (~16kbit/s speech)
    duration_ms = max(500, int(len(result.audio) / 2000 * 1000))
    if proc:
        proc.wait()
    return _json(
        {
            "ok": True,
            "engine": result.engine,
            "voice": result.voice,
            "duration_ms": duration_ms,
            "bytes": len(result.audio),
        }
    )


def handle_tts_stop(ctx: AppContext, arguments: dict) -> str:
    audio_player.stop()
    return _json({"ok": True})


def handle_stt_listen(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.voice import stt as stt_mod

    timeout_ms = int(arguments.get("timeout_ms") or ctx.config.stt.timeout_ms)
    language = arguments.get("language") or ctx.config.stt.language
    cfg = ctx.config.stt
    # Per-call overrides without mutating global config
    from dataclasses import replace

    cfg = replace(cfg, timeout_ms=timeout_ms, language=language)
    result = stt_mod.listen_once(cfg)
    if not result.ok:
        return _json(
            {
                "ok": False,
                "error": result.error,
                "message": result.message,
            }
        )
    return _json(
        {
            "ok": True,
            "text": result.text,
            "confidence": result.confidence,
            "engine": result.engine,
        }
    )


def handle_voice_call_start(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.agent.runtime import AgentRuntime
    from hui_mcp.voice.call_session import get_session

    bg = arguments.get("background_listen")
    session = get_session(ctx, AgentRuntime(ctx))
    session.start(background_listen=bg if isinstance(bg, bool) else None)
    return _json({"ok": True, "active": True})


def handle_voice_call_stop(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.agent.runtime import AgentRuntime
    from hui_mcp.voice.call_session import get_session

    get_session(ctx, AgentRuntime(ctx)).stop()
    return _json({"ok": True, "active": False})


def handle_companion_connection_status(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.cursor_socket_manager import get_watch_status
    from hui_mcp.daemon_client import connection_status

    data = connection_status()
    watch = get_watch_status()
    if not data.get("ok"):
        return _json({**data, **{k: watch.get(k) for k in ("running", "remaining_sec", "expires_at") if k in watch}})
    agent = data.get("agent") or {}
    return _json(
        {
            "ok": True,
            "cursor_online": bool(agent.get("cursor_online")),
            "companion_online": bool(agent.get("companion_online")),
            "cursor_waiting": bool(watch.get("cursor_waiting")),
            "watch_running": watch.get("running"),
            "watch_remaining_sec": watch.get("remaining_sec"),
            "watch_expires_at": watch.get("expires_at"),
        }
    )


def handle_companion_socket_connect(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.cursor_socket_manager import (
        resolve_wait_timeout_sec,
        start_watch,
        wait_for_task,
    )

    watch_minutes = arguments.get("watch_minutes")
    if watch_minutes is None:
        watch_minutes = ctx.config.socket.watch_minutes
    try:
        minutes = float(watch_minutes)
    except (TypeError, ValueError):
        minutes = float(ctx.config.socket.watch_minutes)

    result = start_watch(watch_minutes=minutes)
    if not result.get("ok"):
        return _json(result)

    wait_sec = arguments.get("wait_timeout_sec")
    try:
        wait_sec = float(wait_sec) if wait_sec is not None else None
    except (TypeError, ValueError):
        wait_sec = None
    if wait_sec is None:
        wait_sec = resolve_wait_timeout_sec(None, watch_minutes=minutes)

    if wait_sec > 0:
        wait_result = wait_for_task(timeout_sec=wait_sec, watch_minutes=minutes)
        result["wait"] = wait_result
        if wait_result.get("task_received"):
            result["message"] = "收到 Companion 任务，请立即处理（禁止切换 Cursor 前台）"
        elif wait_result.get("continue_waiting"):
            result["agent_next"] = "companion_socket_wait"

    result["ui_policy"] = (
        "禁止 activate_cursor_app / osascript 切前台；"
        "需切换窗口时仅用 mouse_move + mouse_click；"
        "提前停止监听请 companion_socket_disconnect"
    )
    return _json(result)


def handle_companion_socket_connect_and_wait(ctx: AppContext, arguments: dict) -> str:
    """Connect Socket if offline, then enter companion_socket_wait."""
    from hui_mcp.cursor_socket_manager import get_watch_status, start_watch

    watch_minutes = arguments.get("watch_minutes")
    if watch_minutes is None:
        watch_minutes = ctx.config.socket.watch_minutes
    try:
        minutes = float(watch_minutes)
    except (TypeError, ValueError):
        minutes = float(ctx.config.socket.watch_minutes)

    status = get_watch_status()
    connect: dict
    if status.get("cursor_online"):
        connect = {
            "ok": True,
            "skipped_connect": True,
            "already_running": bool(status.get("running")),
            "cursor_online": True,
            **{k: status[k] for k in ("pid", "expires_at", "remaining_sec") if k in status},
        }
    else:
        connect = start_watch(watch_minutes=minutes)
        if not connect.get("ok"):
            return _json(connect)

    wait_args = {
        k: arguments[k]
        for k in ("timeout_sec", "poll_interval_sec")
        if k in arguments
    }
    wait_payload = json.loads(handle_companion_socket_wait(ctx, wait_args))
    result = {**wait_payload, "connect": connect}
    if connect.get("skipped_connect"):
        prefix = "Socket 已在线，"
    elif connect.get("already_running"):
        prefix = "Socket 已在监听，"
    else:
        prefix = "Socket 已连接，"
    result["message"] = prefix + (wait_payload.get("message") or "已进入监听")
    result["agent_next"] = wait_payload.get("agent_next") or "companion_socket_wait"
    return _json(result)


def handle_companion_socket_wait(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.cursor_socket_manager import resolve_wait_timeout_sec, wait_for_task

    raw_timeout = arguments.get("timeout_sec")
    poll_interval = arguments.get("poll_interval_sec", 2)
    try:
        timeout_sec = float(raw_timeout) if raw_timeout is not None else None
    except (TypeError, ValueError):
        timeout_sec = None
    if timeout_sec is None:
        timeout_sec = resolve_wait_timeout_sec(
            None,
            watch_minutes=float(ctx.config.socket.watch_minutes),
        )
    try:
        poll_interval = float(poll_interval)
    except (TypeError, ValueError):
        poll_interval = 2.0

    result = wait_for_task(
        timeout_sec=timeout_sec,
        poll_interval=poll_interval,
        watch_minutes=float(ctx.config.socket.watch_minutes),
    )
    if result.get("task_received"):
        result["message"] = "收到任务，请 companion_task_pending 后处理"
    elif result.get("continue_waiting"):
        result["agent_next"] = "companion_socket_wait"
        result["message"] = "监听中，请继续 companion_socket_wait（任务完成后亦保持监听）"
    elif result.get("reason") == "watch_expired":
        result["message"] = "监听已到期（默认 12 小时），可重新 companion_socket_connect"
    else:
        result["message"] = "本轮等待超时，Socket 仍在监听，请继续 companion_socket_wait"
    result["ui_policy"] = (
        "禁止 activate_cursor_app / osascript 切前台；"
        "需切换窗口时仅用 mouse_move + mouse_click"
    )
    return _json(result)


def handle_companion_socket_disconnect(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.cursor_socket_manager import stop_watch

    return _json(stop_watch(force=bool(arguments.get("force", False))))


def handle_companion_task_pending(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.daemon_client import get_pending

    data = get_pending()
    if not data.get("ok"):
        return _json(data)
    return _json(
        {
            "ok": True,
            "pending": data.get("pending"),
            "voice_pending": data.get("voice_pending"),
        }
    )


def handle_companion_speak(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.daemon_client import voice_speak

    text = (arguments.get("text") or "").strip()
    if not text:
        return _json({"ok": False, "error": "text required"})
    utterance_id = arguments.get("utterance_id")
    uid = utterance_id.strip() if isinstance(utterance_id, str) and utterance_id.strip() else None
    data = voice_speak(
        text,
        utterance_id=uid,
        final=bool(arguments.get("final", False)),
        interrupt=bool(arguments.get("interrupt", False)),
    )
    return _json(data)



def handle_companion_doc_read_status(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.agent.doc_read_status import (
        build_doc_read_status_response,
        resolve_doc_read_task_id,
    )
    from hui_mcp.agent.doc_read_store import load_doc_read_snapshot
    from hui_mcp.daemon_client import get_doc_read_status, get_pending

    task_id = resolve_doc_read_task_id(
        (arguments.get("task_id") or "").strip() or None,
        get_pending_fn=get_pending,
    )
    if not task_id:
        return _json({"ok": False, "error": "task_id required or no pending task"})

    include_full = bool(arguments.get("full_ocr", True))

    daemon_body = get_doc_read_status(task_id, full_ocr=include_full)
    if daemon_body.get("ok") and "status" in daemon_body:
        return _json(daemon_body)

    snap = load_doc_read_snapshot(task_id)
    body = build_doc_read_status_response(
        ctx,
        snap,
        task_id=task_id,
        include_full_ocr=include_full,
        source="disk" if snap else "none",
    )
    if not daemon_body.get("ok"):
        body["daemon_unreachable"] = daemon_body.get("error")
    return _json(body)


def handle_companion_doc_read_start(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.agent.doc_read_status import resolve_doc_read_task_id
    from hui_mcp.daemon_client import get_pending, start_doc_read

    task_id = resolve_doc_read_task_id(
        (arguments.get("task_id") or "").strip() or None,
        get_pending_fn=get_pending,
    )
    text = (arguments.get("text") or "").strip()
    if not text:
        pending = get_pending()
        if pending.get("ok") and pending.get("pending"):
            text = (pending["pending"].get("text") or "").strip()
    if not task_id:
        return _json({"ok": False, "error": "task_id required or no pending task"})
    data = start_doc_read(task_id, text=text)
    return _json(data)


def _attach_socket_continue_listening(data: dict) -> dict:
    """After task complete, tell Agent to keep socket watch alive."""
    from hui_mcp.cursor_socket_manager import get_watch_status

    watch = get_watch_status()
    data["watch"] = {
        k: watch.get(k)
        for k in ("running", "remaining_sec", "expires_at", "cursor_online", "watch_minutes")
        if k in watch
    }
    if watch.get("running"):
        data["agent_next"] = "companion_socket_wait"
        data["continue_listening"] = True
        data["message"] = (
            "任务已提交，Socket 继续监听新任务；"
            "默认 auto_wait=true 将自动 companion_socket_wait"
        )
    else:
        data["agent_next"] = "companion_socket_connect"
        data["continue_listening"] = False
        data["message"] = (
            "任务已提交，但 Socket 监听未运行；"
            "请 companion_socket_connect 重新连接"
        )
    data["ui_policy"] = (
        "任务完成后保持 Socket 监听；"
        "仅 companion_socket_disconnect 可主动停止"
    )
    return data


def _merge_auto_wait_result(data: dict, wait_payload: dict) -> dict:
    """Merge companion_socket_wait result into task_complete response."""
    data["wait"] = wait_payload
    data["auto_wait"] = True
    if wait_payload.get("task_received"):
        data["task_received"] = True
        if wait_payload.get("pending") is not None:
            data["pending"] = wait_payload.get("pending")
        if wait_payload.get("voice_pending") is not None:
            data["voice_pending"] = wait_payload.get("voice_pending")
        data["agent_next"] = "companion_task_pending"
        data["message"] = "任务已提交，收到新任务，请 companion_task_pending 后处理"
    elif wait_payload.get("continue_waiting"):
        data["continue_waiting"] = True
        data["agent_next"] = "companion_socket_wait"
        data["message"] = (
            "任务已提交，已进入监听；"
            "若 continue_waiting 为 true 请继续 companion_socket_wait"
        )
    elif wait_payload.get("reason") == "watch_expired":
        data["agent_next"] = "companion_socket_connect"
        data["continue_listening"] = False
        data["message"] = "任务已提交，监听已到期，请 companion_socket_connect 重新连接"
    elif wait_payload.get("ok") is False:
        data["agent_next"] = "companion_socket_connect"
        data["continue_listening"] = False
        err = wait_payload.get("error")
        data["message"] = f"任务已提交，但自动监听失败：{err}"
    else:
        data["agent_next"] = "companion_socket_wait"
        data["message"] = "任务已提交，本轮等待结束，请继续 companion_socket_wait"
    return data


def _maybe_auto_wait_after_complete(
    ctx: AppContext, arguments: dict, data: dict
) -> dict:
    """Optionally invoke companion_socket_wait immediately after task complete."""
    auto_wait = arguments.get("auto_wait", True)
    if auto_wait is False or str(auto_wait).lower() in ("0", "false", "no"):
        return data
    if not data.get("continue_listening"):
        return data

    wait_args: dict = {}
    for key in ("timeout_sec", "poll_interval_sec"):
        if key in arguments:
            wait_args[key] = arguments[key]
    wait_payload = json.loads(handle_companion_socket_wait(ctx, wait_args))
    return _merge_auto_wait_result(data, wait_payload)


def handle_companion_task_complete(ctx: AppContext, arguments: dict) -> str:
    from hui_mcp.daemon_client import complete_task, voice_turn_complete

    task_id = (arguments.get("task_id") or arguments.get("utterance_id") or "").strip()
    reply = (arguments.get("reply") or "").strip()
    if not task_id or not reply:
        return _json({"ok": False, "error": "task_id and reply required"})
    channel = (arguments.get("channel") or "").lower()
    ok_flag = bool(arguments.get("ok", True))
    if channel == "voice":
        data = voice_turn_complete(task_id, reply, ok=ok_flag)
        if data.get("ok"):
            data = _attach_socket_continue_listening(data)
            data = _maybe_auto_wait_after_complete(ctx, arguments, data)
            return _json(data)
        return _json(data)
    data = complete_task(task_id, reply, ok=ok_flag)
    if data.get("ok"):
        data = _attach_socket_continue_listening(data)
        data = _maybe_auto_wait_after_complete(ctx, arguments, data)
        return _json(data)
    return _json(data)


TOOL_HANDLERS = {
    "get_recent_frames": handle_get_recent_frames,
    "get_screenshot": handle_get_screenshot,
    "get_screen_info": handle_get_screen_info,
    "check_permissions": handle_check_permissions,
    "activate_document_app": handle_activate_document_app,
    "activate_cursor_app": handle_activate_cursor_app,
    "mouse_get_position": handle_mouse_get_position,
    "mouse_move": handle_mouse_move,
    "mouse_click": handle_mouse_click,
    "mouse_drag": handle_mouse_drag,
    "mouse_scroll": handle_mouse_scroll,
    "keyboard_press": handle_keyboard_press,
    "keyboard_hotkey": handle_keyboard_hotkey,
    "keyboard_type": handle_keyboard_type,
    "tts_speak": handle_tts_speak,
    "tts_stop": handle_tts_stop,
    "stt_listen": handle_stt_listen,
    "voice_call_start": handle_voice_call_start,
    "voice_call_stop": handle_voice_call_stop,
    "companion_connection_status": handle_companion_connection_status,
    "companion_socket_connect": handle_companion_socket_connect,
    "companion_socket_connect_and_wait": handle_companion_socket_connect_and_wait,
    "companion_socket_wait": handle_companion_socket_wait,
    "companion_socket_disconnect": handle_companion_socket_disconnect,
    "companion_task_pending": handle_companion_task_pending,
    "companion_doc_read_status": handle_companion_doc_read_status,
    "companion_doc_read_start": handle_companion_doc_read_start,
    "companion_task_complete": handle_companion_task_complete,
    "companion_speak": handle_companion_speak,
}
