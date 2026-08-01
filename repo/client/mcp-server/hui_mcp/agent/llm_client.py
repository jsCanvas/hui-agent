"""OpenAI-compatible chat completions client (vision + tools)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from hui_mcp.config import LlmConfig

log = logging.getLogger("hui_mcp.llm")


def image_to_data_url(path: str | Path) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    raw = p.read_bytes()
    if len(raw) > 4_500_000:
        log.warning("image too large for LLM: %s", p)
        return None
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


class LlmClient:
    def __init__(self, cfg: LlmConfig) -> None:
        self.cfg = cfg
        base = cfg.base_url.rstrip("/")
        self._url = f"{base}/chat/completions"

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.cfg.timeout_sec) as client:
            resp = client.post(self._url, headers=headers, json=body)
            if resp.status_code >= 400:
                raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
            return resp.json()

    @staticmethod
    def assistant_message(payload: dict[str, Any]) -> dict[str, Any]:
        choice = (payload.get("choices") or [{}])[0]
        return choice.get("message") or {}

    @staticmethod
    def tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        return list(message.get("tool_calls") or [])

    @staticmethod
    def text_content(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def dump_tool_result(name: str, outcome: dict[str, Any]) -> str:
        return json.dumps({"tool": name, "outcome": outcome}, ensure_ascii=False)
