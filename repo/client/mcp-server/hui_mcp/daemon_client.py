"""HTTP client for the capture daemon (MCP stdio runs in a separate process)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

DAEMON_PORT = int(os.environ.get("HUI_AGENT_DAEMON_PORT", "18766"))
BASE = f"http://127.0.0.1:{DAEMON_PORT}"


def _request(method: str, path: str, body: dict | None = None, *, timeout: float = 5) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"daemon unreachable: {e}"}


def get_pending() -> dict:
    return _request("GET", "/agent/pending", timeout=2)


def get_doc_read_status(task_id: str, *, full_ocr: bool = True) -> dict:
    q = urllib.parse.urlencode({"task_id": task_id, "full_ocr": "1" if full_ocr else "0"})
    return _request("GET", f"/agent/doc_read?{q}", timeout=5)


def start_doc_read(task_id: str = "", *, text: str = "") -> dict:
    body: dict = {}
    if task_id:
        body["task_id"] = task_id
    if text:
        body["text"] = text
    return _request("POST", "/agent/doc_read/start", body or None, timeout=10)


def complete_task(task_id: str, reply: str, *, ok: bool = True) -> dict:
    return _request(
        "POST",
        "/agent/complete",
        {"task_id": task_id, "reply": reply, "ok": ok},
    )


def cancel_task(task_id: str = "", *, reason: str = "用户终止") -> dict:
    body: dict = {"reason": reason}
    if task_id:
        body["task_id"] = task_id
    return _request("POST", "/agent/cancel", body, timeout=5)


def connection_status() -> dict:
    return _request("GET", "/health", timeout=2)


def notify_wait_state(waiting: bool) -> dict:
    return _request(
        "POST",
        "/agent/wait/notify",
        {"waiting": bool(waiting)},
        timeout=2,
    )


def request_automation_consent(tool: str, *, timeout: float = 130) -> dict:
    """Ask daemon (Companion UI) to confirm mouse/keyboard automation."""
    return _request(
        "POST",
        "/automation/consent/request",
        {"tool": tool},
        timeout=timeout,
    )


def voice_speak(
    text: str,
    *,
    utterance_id: str | None = None,
    final: bool = False,
    interrupt: bool = False,
) -> dict:
    body: dict = {
        "text": text,
        "final": final,
        "interrupt": interrupt,
    }
    if utterance_id:
        body["utterance_id"] = utterance_id
    timeout = max(30, min(200, int(len(text) * 0.15) + 20))
    return _request("POST", "/voice/speak", body, timeout=timeout)


def voice_turn_complete(utterance_id: str, reply: str, *, ok: bool = True) -> dict:
    return _request(
        "POST",
        "/voice/turn/complete",
        {"utterance_id": utterance_id, "reply": reply, "ok": ok},
        timeout=10,
    )
