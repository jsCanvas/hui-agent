"""Start/stop Cursor Socket relay (cursor-socket-client) from MCP."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from hui_mcp.daemon_client import connection_status

DEFAULT_WATCH_MINUTES = 720.0  # 12 hours
MAX_WATCH_MINUTES = 720.0
DEFAULT_WAIT_TIMEOUT_SEC = DEFAULT_WATCH_MINUTES * 60.0  # 12h, aligned with watch
MAX_WAIT_TIMEOUT_SEC = DEFAULT_WAIT_TIMEOUT_SEC

PID_FILE = Path.home() / ".hui-agent" / "cursor-socket.pid"
STATE_FILE = Path.home() / ".hui-agent" / "cursor-socket-state.json"
WAIT_STATE_FILE = Path.home() / ".hui-agent" / "cursor-wait-state.json"
CLIENT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = CLIENT_ROOT / "scripts" / "cursor-socket-client.py"
BG_SCRIPT = CLIENT_ROOT / "scripts" / "run-cursor-socket-background.sh"
MCP_DIR = CLIENT_ROOT / "mcp-server"
VENV_PY = MCP_DIR / ".venv" / "bin" / "python"


def _python() -> str:
    if VENV_PY.is_file():
        return str(VENV_PY)
    return sys.executable


def _read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _write_state(payload: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cursor_online_via_http() -> bool:
    """Query daemon /health from MCP stdio or other processes (must not recurse)."""
    data = connection_status()
    if not data.get("ok"):
        return False
    agent = data.get("agent") or {}
    return bool(agent.get("cursor_online"))


def _cursor_online_inprocess() -> bool:
    try:
        from hui_mcp.cursor_relay import get_relay

        return get_relay().is_cursor_online()
    except Exception:
        return False


def _read_wait_state() -> dict:
    if not WAIT_STATE_FILE.is_file():
        return {"waiting": False}
    try:
        data = json.loads(WAIT_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"waiting": False}
    except (json.JSONDecodeError, OSError):
        return {"waiting": False}


def read_watch_metadata() -> dict:
    """PID / watch / wait state from local files only (safe inside daemon /health)."""
    pid = _read_pid()
    alive = pid is not None and _is_alive(pid)
    if pid and not alive:
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        pid = None
    state: dict = {}
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    expires_at = state.get("expires_at")
    remaining_sec = None
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at))
            remaining_sec = max(0, int((exp - datetime.now(timezone.utc)).total_seconds()))
        except ValueError:
            remaining_sec = None
    wait = _read_wait_state()
    return {
        "ok": True,
        "running": alive,
        "pid": pid,
        "cursor_waiting": bool(wait.get("waiting")),
        "cursor_wait_since": wait.get("since"),
        "watch_minutes": state.get("watch_minutes"),
        "started_at": state.get("started_at"),
        "expires_at": expires_at,
        "remaining_sec": remaining_sec,
    }


def get_watch_status(*, local_relay: bool = False) -> dict:
    meta = read_watch_metadata()
    if local_relay:
        meta["cursor_online"] = _cursor_online_inprocess()
    else:
        meta["cursor_online"] = _cursor_online_via_http()
    return meta


def begin_cursor_wait() -> None:
    payload = {
        "waiting": True,
        "since": datetime.now(timezone.utc).isoformat(),
    }
    WAIT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    WAIT_STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    from hui_mcp.daemon_client import notify_wait_state

    notify_wait_state(True)


def end_cursor_wait() -> None:
    try:
        WAIT_STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    from hui_mcp.daemon_client import notify_wait_state

    notify_wait_state(False)


def clear_cursor_wait_state() -> None:
    try:
        WAIT_STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def stop_watch(*, force: bool = False) -> dict:
    pid = _read_pid()
    if not pid or not _is_alive(pid):
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        clear_cursor_wait_state()
        return {"ok": True, "stopped": False, "message": "not running"}

    sig = signal.SIGTERM
    try:
        os.kill(pid, sig)
        for _ in range(20):
            if not _is_alive(pid):
                break
            time.sleep(0.1)
        if _is_alive(pid) and force:
            os.kill(pid, signal.SIGKILL)
    except OSError as e:
        return {"ok": False, "error": str(e)}

    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    clear_cursor_wait_state()
    return {"ok": True, "stopped": True, "pid": pid}


def resolve_wait_timeout_sec(
    timeout_sec: float | None,
    *,
    watch_minutes: float | None = None,
) -> float:
    """Clamp wait timeout to [1s, watch duration] (default 12h)."""
    minutes = float(watch_minutes if watch_minutes is not None else DEFAULT_WATCH_MINUTES)
    minutes = max(1.0, min(minutes, MAX_WATCH_MINUTES))
    max_sec = min(minutes * 60.0, MAX_WAIT_TIMEOUT_SEC)
    if timeout_sec is None:
        return max_sec
    return max(1.0, min(float(timeout_sec), max_sec))


def wait_for_task(
    *,
    timeout_sec: float | None = None,
    poll_interval: float = 2.0,
    watch_minutes: float | None = None,
) -> dict:
    """Poll Daemon pending until task arrives, watch expires, or timeout."""
    from hui_mcp.daemon_client import get_pending

    begin_cursor_wait()
    try:
        timeout_sec = resolve_wait_timeout_sec(timeout_sec, watch_minutes=watch_minutes)
        poll_interval = max(0.5, min(float(poll_interval), 10.0))
        watch = get_watch_status()
        remaining = watch.get("remaining_sec")
        if remaining is not None:
            timeout_sec = min(timeout_sec, max(1.0, float(remaining)))
        deadline = time.time() + timeout_sec

        while time.time() < deadline:
            watch = get_watch_status()
            if not watch.get("cursor_online") and not watch.get("running"):
                return {
                    "ok": False,
                    "error": "socket watch not running",
                    "watch": watch,
                }
            remaining = watch.get("remaining_sec")
            if remaining is not None and remaining <= 0:
                return {
                    "ok": True,
                    "task_received": False,
                    "reason": "watch_expired",
                    "watch": watch,
                }

            data = get_pending()
            if data.get("ok"):
                pending = data.get("pending")
                voice = data.get("voice_pending")
                if pending or voice:
                    return {
                        "ok": True,
                        "task_received": True,
                        "pending": pending,
                        "voice_pending": voice,
                        "watch": watch,
                    }

            time.sleep(poll_interval)

        watch = get_watch_status()
        return {
            "ok": True,
            "task_received": False,
            "reason": "poll_timeout",
            "watch": watch,
            "continue_waiting": bool(watch.get("running") and (watch.get("remaining_sec") or 0) > 0),
        }
    finally:
        end_cursor_wait()


def _spawn_background_socket(watch_minutes: float, log_path: Path) -> subprocess.Popen | None:
    """Start socket client in detached background (no Cursor focus)."""
    if BG_SCRIPT.is_file():
        proc = subprocess.Popen(
            ["/bin/bash", str(BG_SCRIPT), str(watch_minutes)],
            cwd=str(CLIENT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )
        try:
            out, _ = proc.communicate(timeout=3)
            pid = int((out or "").strip().splitlines()[-1])
            if pid > 0:
                PID_FILE.parent.mkdir(parents=True, exist_ok=True)
                PID_FILE.write_text(str(pid), encoding="utf-8")
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        return proc

    cmd = [_python(), str(SCRIPT), "--watch-minutes", str(watch_minutes)]
    with open(log_path, "a", encoding="utf-8") as log_f:
        return subprocess.Popen(
            cmd,
            cwd=str(CLIENT_ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def start_watch(*, watch_minutes: float = DEFAULT_WATCH_MINUTES) -> dict:
    """Spawn cursor-socket-client in watch mode; wait until cursor_online or timeout."""
    if not SCRIPT.is_file():
        return {"ok": False, "error": f"missing script: {SCRIPT}"}

    status = get_watch_status()
    if status.get("running") and status.get("cursor_online"):
        return {
            "ok": True,
            "already_running": True,
            "cursor_online": True,
            "agent_next": "companion_socket_wait",
            **{k: status[k] for k in ("pid", "expires_at", "remaining_sec") if k in status},
        }

    stop_watch()

    clear_cursor_wait_state()

    watch_minutes = max(1.0, min(float(watch_minutes), MAX_WATCH_MINUTES))
    started_at = datetime.now(timezone.utc)
    expires_at = started_at.timestamp() + watch_minutes * 60.0
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    _write_state(
        {
            "watch_minutes": watch_minutes,
            "started_at": started_at.isoformat(),
            "expires_at": expires_iso,
        }
    )

    log_dir = Path.home() / ".hui-agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cursor-socket.log"

    proc = _spawn_background_socket(watch_minutes, log_path)
    if proc is None:
        return {"ok": False, "error": "failed to spawn background socket"}

    pid = _read_pid() or proc.pid

    deadline = time.time() + 12.0
    while time.time() < deadline:
        if _cursor_online_via_http():
            duration = (
                "12 小时"
                if int(watch_minutes) == int(DEFAULT_WATCH_MINUTES)
                else f"{int(watch_minutes)} 分钟"
            )
            return {
                "ok": True,
                "cursor_online": True,
                "pid": pid,
                "watch_minutes": watch_minutes,
                "expires_at": expires_iso,
                "log": str(log_path),
                "background_terminal": True,
                "message": (
                    f"后台 Socket 已连接（PID {pid}），监听 {duration}。"
                    "提前停止请调用 companion_socket_disconnect；"
                    "不会切换 Cursor 前台；请调用 companion_socket_wait 等待任务。"
                ),
                "agent_next": "companion_socket_wait",
            }
        if proc.poll() is not None and not _read_pid():
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-800:] if log_path.is_file() else ""
            return {
                "ok": False,
                "error": "cursor-socket-client exited before registration",
                "exit_code": proc.returncode,
                "log_tail": tail,
            }
        time.sleep(0.25)

    return {
        "ok": False,
        "error": "socket registration timeout (12s)",
        "pid": pid,
        "cursor_online": _cursor_online_via_http(),
        "log": str(log_path),
    }
