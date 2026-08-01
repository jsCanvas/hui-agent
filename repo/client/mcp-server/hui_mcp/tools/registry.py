"""Shared tool invocation for MCP stdio and Socket Bridge."""

from __future__ import annotations

import json
from typing import Any

from hui_mcp.context import AppContext
from hui_mcp.tools.handlers import TOOL_HANDLERS
from hui_mcp.automation_consent import ensure_automation_consent


def invoke_tool(ctx: AppContext, name: str, arguments: dict | None = None) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {
            "ok": False,
            "error": {"code": "TOOL_NOT_FOUND", "message": f"unknown tool: {name}"},
        }
    blocked = ensure_automation_consent(ctx, name)
    if blocked:
        return blocked
    try:
        raw = handler(ctx, arguments or {})
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("ok") is False:
            return {"ok": False, "error": data.get("error", data)}
        return {"ok": True, "result": data}
    except json.JSONDecodeError:
        return {"ok": True, "result": {"text": raw}}
    except Exception as e:
        return {"ok": False, "error": {"code": "TOOL_ERROR", "message": str(e)}}


def list_tool_names() -> list[str]:
    return sorted(TOOL_HANDLERS.keys())
