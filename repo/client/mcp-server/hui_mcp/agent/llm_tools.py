"""OpenAI function schemas for desktop MCP tools (Agent loop)."""

from __future__ import annotations

from hui_mcp.tools.schemas import TOOLS

# Desktop control only — voice tools are handled by Companion UI.
_AGENT_TOOL_NAMES = frozenset(
    {
        "get_recent_frames",
        "get_screenshot",
        "get_screen_info",
        "check_permissions",
        "mouse_get_position",
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_press",
        "keyboard_hotkey",
        "keyboard_type",
    }
)


def openai_tool_definitions() -> list[dict]:
    out: list[dict] = []
    for tool in TOOLS:
        if tool.name not in _AGENT_TOOL_NAMES:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or tool.name,
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    return out
