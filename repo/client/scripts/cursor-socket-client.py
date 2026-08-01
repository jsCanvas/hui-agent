#!/usr/bin/env python3
"""Cursor Socket relay — keep long connection; Cursor AI is the brain.

  cd hui-agent/repo/client && python3 scripts/cursor-socket-client.py

Manual / MCP watch mode (12 hours default):
  python3 scripts/cursor-socket-client.py --watch-minutes 720

Maintains ``cursor`` registration so Companion tasks can relay. On task.request
writes active-task.json and notifies Agent (no Cursor foreground activation).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp-server"
_VENV_PY = _MCP / ".venv" / "bin" / "python"
_ACTIVE_TASK = Path.home() / ".hui-agent" / "active-task.json"
_ACTIVE_VOICE = Path.home() / ".hui-agent" / "active-voice.json"
_PID_FILE = Path.home() / ".hui-agent" / "cursor-socket.pid"

if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    os.execv(str(_VENV_PY), [str(_VENV_PY), __file__, *sys.argv[1:]])

from datetime import datetime, timezone


def load_config() -> dict:
    path = Path.home() / ".hui-agent" / "config.json"
    if not path.exists():
        raise FileNotFoundError(f"missing config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_pid() -> None:
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid() -> None:
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def send_line(sock: socket.socket, obj: dict) -> None:
    sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode())


def recv_line(sock: socket.socket) -> dict:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return json.loads(buf.decode())


def write_active_task(task_id: str, text: str, *, doc_read: bool = False) -> None:
    _ACTIVE_TASK.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "text": text,
        "channel": "text",
        "doc_read": doc_read,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIVE_TASK.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_active_voice(
    utterance_id: str,
    text: str,
    session_id: str = "",
    *,
    duplex: dict | None = None,
) -> None:
    _ACTIVE_VOICE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "utterance_id": utterance_id,
        "session_id": session_id,
        "text": text,
        "channel": "voice",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if duplex:
        payload["duplex"] = duplex
    _ACTIVE_VOICE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(title: str, subtitle: str, body: str) -> None:
    if sys.platform != "darwin":
        return
    import subprocess

    safe = body[:80].replace('"', "'")
    script = f'display notification "{safe}" with title "{title}" subtitle "{subtitle}"'
    subprocess.run(["osascript", "-e", script], check=False)


def resolve_cursor_trigger_mode(cfg: dict) -> str:
    """Map config cursor_trigger to socket auto-trigger behavior."""
    mode = str(cfg.get("doc_read", {}).get("cursor_trigger", "notify_only")).lower()
    if mode == "osascript":
        return "osascript"
    if mode in ("notify", "background"):
        return "background"
    return "notify_only"


def trigger_cursor_agent(
    *,
    background: bool = False,
    notify_only: bool = False,
    task_id: str = "",
    text: str = "",
    sync: bool = False,
) -> bool:
    script = _ROOT / "scripts" / "trigger-cursor-companion-task.sh"
    if not script.is_file():
        return False
    import subprocess

    args = ["/bin/bash", str(script)]
    if notify_only:
        args.append("--notify-only")
    elif background:
        args.append("--background")
    env = os.environ.copy()
    if task_id:
        env["HUI_TASK_ID"] = task_id
    if text:
        env["HUI_TASK_TEXT"] = text
    if sync:
        result = subprocess.run(
            args,
            cwd=str(_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
        )
        return result.returncode == 0
    subprocess.Popen(
        args,
        cwd=str(_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def copy_followup_to_clipboard(task_id: str, text: str) -> bool:
    import subprocess

    env = os.environ.copy()
    env["HUI_TASK_ID"] = task_id
    env["HUI_TASK_TEXT"] = text
    script = _ROOT / "scripts" / "trigger-cursor-companion-task.sh"
    if not script.is_file():
        return False
    result = subprocess.run(
        ["/bin/bash", str(script), "--notify-only"],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result.returncode == 0


def auto_trigger_cursor_agent(task_id: str, text: str, *, doc_read: bool) -> None:
    """On socket task: notify + optional Cursor trigger (default notify_only, no UI switch)."""
    cfg = load_config()
    mode = resolve_cursor_trigger_mode(cfg)

    if doc_read:
        notify(
            "Companion 文档任务",
            f"task {task_id[:8]}",
            "请 companion_socket_wait 处理（不切前台）",
        )
    else:
        notify(
            "Companion 文字任务",
            f"task {task_id[:8]}",
            "新任务；请 companion_socket_wait（不切前台）",
        )

    copy_followup_to_clipboard(task_id, text)

    if mode == "osascript":
        trigger_cursor_agent(task_id=task_id, text=text, sync=True)
    elif mode == "background":
        trigger_cursor_agent(task_id=task_id, text=text, sync=True, background=True)


def connect_and_serve(
    host: str,
    port: int,
    token: str,
    *,
    deadline: float | None = None,
) -> None:
    sock = socket.create_connection((host, port), timeout=15)
    sock.settimeout(None)
    write_pid()
    try:
        send_line(sock, {"type": "auth", "token": token})
        auth = recv_line(sock)
        if auth.get("type") != "auth.ok":
            raise RuntimeError(f"auth failed: {auth}")

        send_line(sock, {"type": "agent.register", "role": "cursor", "auto": False})
        reg = recv_line(sock)
        if reg.get("type") != "agent.registered":
            raise RuntimeError(f"register failed: {reg}")

        if deadline:
            remaining = max(0, int(deadline - time.time()))
            notify(
                "Companion Socket",
                "已连接",
                f"监听任务 {remaining // 60} 分钟；收到任务将自动启动 Agent",
            )

        print(
            f"✓ Cursor relay connected ({host}:{port})\n"
            "  等待 Companion task.request / voice.user.message …\n",
            file=sys.stderr,
        )

        while True:
            if deadline and time.time() >= deadline:
                print("watch timeout reached, exiting", file=sys.stderr)
                notify("Companion Socket", "监听结束", "等待时间已到，连接已关闭")
                break

            if deadline:
                sock.settimeout(max(0.2, min(1.0, deadline - time.time())))
            try:
                msg = recv_line(sock)
            except socket.timeout:
                continue
            finally:
                sock.settimeout(None)

            mtype = msg.get("type")
            if mtype == "task.request":
                task_id = msg.get("task_id") or ""
                text = msg.get("text") or ""
                doc_read = bool(msg.get("doc_read") or msg.get("no_focus"))
                write_active_task(task_id, text, doc_read=doc_read)
                auto_trigger_cursor_agent(task_id, text, doc_read=doc_read)
                print(
                    f"\n=== 文字任务 ===\ntask_id: {task_id}\ndoc_read: {doc_read}\ntext: {text}\n",
                    file=sys.stderr,
                )
            elif mtype == "voice.user.message":
                utterance_id = msg.get("utterance_id") or ""
                text = msg.get("text") or ""
                session_id = msg.get("session_id") or ""
                duplex = msg.get("duplex") if isinstance(msg.get("duplex"), dict) else None
                write_active_voice(utterance_id, text, session_id, duplex=duplex)
                notify("Companion 通话", f"utterance {utterance_id[:8]}", text)
                auto_trigger_cursor_agent(utterance_id, text, doc_read=False)
            elif mtype == "voice.stt.partial":
                partial = (msg.get("text") or "")[:60]
                print(f"[stt.partial] {partial}", file=sys.stderr)
            elif mtype == "ping":
                send_line(sock, {"type": "pong"})
            elif mtype == "error":
                print(f"[error] {msg.get('code')}: {msg.get('message')}", file=sys.stderr)
            else:
                print(f"[socket] {json.dumps(msg, ensure_ascii=False)}", file=sys.stderr)
    finally:
        clear_pid()
        sock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cursor Socket relay client")
    parser.add_argument(
        "--watch-minutes",
        type=float,
        default=0,
        help="Listen for tasks then exit (0 = reconnect forever)",
    )
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    sock_cfg = cfg.get("socket", {})
    host = sock_cfg.get("host", "127.0.0.1")
    port = int(sock_cfg.get("port", 18765))
    token = sock_cfg.get("token", "")
    if not token:
        print("error: missing socket.token in ~/.hui-agent/config.json", file=sys.stderr)
        return 1

    watch_minutes = float(args.watch_minutes or 0)
    if watch_minutes > 0:
        deadline = time.time() + watch_minutes * 60.0
        try:
            connect_and_serve(host, port, token, deadline=deadline)
        except KeyboardInterrupt:
            print("\nbye", file=sys.stderr)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0

    backoff = 1.0
    while True:
        try:
            connect_and_serve(host, port, token)
            print("connection closed, reconnecting…", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nbye", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"error: {e}; retry in {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


if __name__ == "__main__":
    raise SystemExit(main())
