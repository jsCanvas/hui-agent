"""MCP stdio server entry."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from hui_mcp.config import AppConfig
from hui_mcp.context import AppContext
from hui_mcp.tools.registry import invoke_tool
from hui_mcp.tools.schemas import TOOLS
from hui_mcp.voice import manager as voice_manager

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[hui-mcp] %(message)s")
log = logging.getLogger("hui_mcp")


def _build_context() -> AppContext:
    cfg = AppConfig.load()
    if cfg.tts.auto_start_proxy:
        try:
            voice_manager.ensure_proxy(cfg)
            log.info("Edge TTS proxy ready at %s", cfg.tts.url)
        except Exception as e:
            log.warning("Edge TTS proxy not started: %s", e)
    ctx = AppContext(config=cfg)
    ctx.ensure_ring()
    log.info("Frame ring buffer started (10fps, 50 slots)")
    return ctx


@asynccontextmanager
async def app_lifespan(_server: Server) -> AsyncIterator[AppContext]:
    ctx = _build_context()
    try:
        yield ctx
    finally:
        if ctx.ring:
            ctx.ring.stop()
        voice_manager.stop_proxy()


server = Server("hui-agent-desktop", lifespan=app_lifespan)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    ctx: AppContext = server.request_context.lifespan_context
    import json

    try:
        outcome = await asyncio.to_thread(invoke_tool, ctx, name, arguments or {})
        if outcome.get("ok"):
            payload = outcome.get("result", outcome)
        else:
            payload = {"ok": False, "error": outcome.get("error")}
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except Exception as e:
        log.exception("tool %s failed", name)
        return [types.TextContent(type="text", text=f'{{"ok": false, "error": "{e}"}}')]


async def run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="hui-agent-desktop",
                server_version="0.1.5",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
