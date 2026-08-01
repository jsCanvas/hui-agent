#!/usr/bin/env python3
"""Long-running companion_socket_wait loop until watch expires."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp-server"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.cursor_socket_manager import get_watch_status
from hui_mcp.daemon_client import get_pending
from hui_mcp.tools.registry import invoke_tool


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def pending_active() -> bool:
    data = get_pending()
    if not data.get("ok"):
        return False
    return bool(data.get("pending") or data.get("voice_pending"))


def main() -> int:
    ctx = AppContext(config=AppConfig.load())
    log("long companion_socket_wait daemon started")
    rounds = 0

    while True:
        watch = get_watch_status()
        if watch.get("remaining_sec") is not None and watch.get("remaining_sec") <= 0:
            log("watch expired, daemon stopping")
            return 0
        if not watch.get("running"):
            log("socket watch not running, daemon stopping")
            return 1

        rounds += 1
        log(f"round {rounds}: blocking wait (up to remaining watch window)")
        out = invoke_tool(ctx, "companion_socket_wait", {"poll_interval_sec": 2})
        result = out.get("result") or {}
        print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)

        if not result.get("ok"):
            log(f"wait error: {result.get('error')!r}, retry in 10s")
            time.sleep(10)
            continue

        if result.get("task_received"):
            pending = result.get("pending") or result.get("voice_pending") or {}
            log(f"task received: {json.dumps(pending, ensure_ascii=False)}")
            log("waiting for pending queue to clear before next wait round...")
            while pending_active():
                time.sleep(3)
            log("pending cleared, resuming long listen")
            continue

        reason = result.get("reason")
        if reason == "watch_expired":
            log("watch expired during wait, daemon stopping")
            return 0
        if result.get("continue_waiting") or reason == "poll_timeout":
            log("poll timeout, continuing long listen")
            continue

        log(f"unexpected reason={reason!r}, retry in 5s")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
