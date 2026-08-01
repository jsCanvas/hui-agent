"""Built-in local edge model — structure OCR text without remote LLM / api_key."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s*)?"
    r"(?:第[一二三四五六七八九十百零\d]+节|[\d]+[\.、]\s*[\d]*\.?\s*)"
    r".{2,80}$"
)
_SUBHEAD_RE = re.compile(
    r"^(?:#{1,4}\s*)?"
    r"(?:[\d]+[\.、][\d]*[\.、]?|[（(][一二三四五六七八九十\d]+[)）])"
    r".{2,60}$"
)
_BULLET_RE = re.compile(r"^[\-*•●○▪▸►]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^[\d]+[\.、)]\s*(.+)$")
_FLOW_RE = re.compile(r"(步骤|流程|首先|然后|接着|最后|→|->|⇒)")
_API_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH)\s+[/\w\-{}]+|"
    r"[/][\w\-/{}]+(?:\?[\w=&]+)?|"
    r"\b(?:api|API|接口|endpoint)\b",
    re.I,
)
_FIELD_RE = re.compile(
    r"[`'\"]?([a-zA-Z_][\w]{2,30})[`'\"]?\s*[:：]|"
    r"(\w+Id|\w+ID|\w+Code|\w+Name|\w+Type|\w+Status)\b"
)
_KEY_PHRASES = (
    "运费",
    "计费",
    "拆包",
    "面单",
    "结算",
    "极兔",
    "发货",
    "包裹",
    "订单",
    "买家",
    "卖家",
    "流程图",
    "示意图",
)


@dataclass
class _OutlineParts:
    headings: list[str]
    subheads: list[str]
    bullets: list[str]
    flows: list[str]
    apis: list[str]
    fields: list[str]
    key_lines: list[str]


def _clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    return line


def _collect_parts(lines: list[str]) -> _OutlineParts:
    headings: list[str] = []
    subheads: list[str] = []
    bullets: list[str] = []
    flows: list[str] = []
    apis: list[str] = []
    fields: list[str] = []
    key_lines: list[str] = []
    seen: set[str] = set()

    def add(bucket: list[str], text: str, *, limit: int = 24) -> None:
        t = _clean_line(text)
        if len(t) < 4 or t in seen:
            return
        seen.add(t)
        if len(bucket) < limit:
            bucket.append(t)

    for raw in lines:
        line = _clean_line(raw)
        if len(line) < 3:
            continue
        if _HEADING_RE.match(line):
            add(headings, line, limit=12)
            continue
        if _SUBHEAD_RE.match(line):
            add(subheads, line, limit=20)
            continue
        m = _BULLET_RE.match(line)
        if m:
            add(bullets, m.group(1))
            continue
        m = _NUMBERED_RE.match(line)
        if m and len(m.group(1)) >= 4:
            add(bullets, m.group(1))
            continue
        if _FLOW_RE.search(line) and len(line) >= 6:
            add(flows, line, limit=16)
        for hit in _API_RE.findall(line):
            token = hit if isinstance(hit, str) else hit[0]
            if token:
                add(apis, token if token.startswith("/") or token.isupper() else line, limit=20)
        for grp in _FIELD_RE.findall(line):
            name = next((g for g in grp if g), "")
            if name and not name.isdigit():
                add(fields, name, limit=30)
        if any(k in line for k in _KEY_PHRASES) and len(line) >= 8:
            add(key_lines, line, limit=20)

    return _OutlineParts(headings, subheads, bullets, flows, apis, fields, key_lines)


def _section_block(title: str, items: list[str]) -> str:
    if not items:
        return ""
    body = "\n".join(f"- {x}" for x in items)
    return f"### {title}\n{body}\n"


def build_local_outline(section: str, ocr_text: str, *, max_chars: int = 6000) -> str:
    """Return a structured Chinese outline from OCR plain text (fully offline)."""
    text = (ocr_text or "").strip()
    if len(text) < 40:
        return ""

    lines = [_clean_line(ln) for ln in text.splitlines() if _clean_line(ln)]
    parts = _collect_parts(lines)

    chunks = [
        f"## {section} — 本地结构化大纲",
        f"- OCR 原文约 {len(text)} 字，提取 {len(lines)} 行",
        "",
        _section_block("章节标题", parts.headings),
        _section_block("小节", parts.subheads),
        _section_block("要点列表", parts.bullets),
        _section_block("流程/步骤", parts.flows),
        _section_block("接口/API", parts.apis),
        _section_block("字段/标识", parts.fields[:18]),
        _section_block("业务关键词句", parts.key_lines),
    ]
    outline = "\n".join(c for c in chunks if c).strip()
    if len(outline) > max_chars:
        outline = outline[: max_chars - 20] + "\n\n…（大纲已截断）"
    return outline


def edge_model_available() -> bool:
    """Built-in rule engine is always available."""
    return True


def build_outline(section: str, ocr_text: str, doc_cfg) -> tuple[str, str]:
    """Build outline using configured edge model.

    Returns (outline_text, model_used) where model_used is builtin|gguf|gguf→builtin.
    """
    from hui_mcp.config import DocReadConfig

    doc: DocReadConfig = doc_cfg.doc_read
    mode = (doc.edge_model or "auto").lower()

    if mode == "builtin":
        return build_local_outline(section, ocr_text), "builtin"

    if mode in ("gguf", "auto"):
        try:
            from hui_mcp.agent.edge_gguf import build_gguf_outline, gguf_model_ready

            if gguf_model_ready(doc):
                outline = build_gguf_outline(section, ocr_text, doc)
                if outline.strip():
                    return outline, "gguf"
                if mode == "gguf":
                    pass
            elif mode == "gguf":
                raise FileNotFoundError("GGUF model not ready")
        except Exception as e:
            if mode == "gguf":
                raise
            import logging

            logging.getLogger("hui_mcp.edge_model").warning(
                "GGUF unavailable (%s), fallback to builtin", e
            )

    return build_local_outline(section, ocr_text), "builtin"


def edge_outline_status(doc_cfg) -> dict:
    from hui_mcp.agent.edge_gguf import gguf_status, gguf_model_ready

    doc = doc_cfg.doc_read
    st = gguf_status(doc)
    st["edge_model"] = doc.edge_model
    st["builtin_ready"] = True
    st["gguf_ready"] = gguf_model_ready(doc)
    st["effective"] = (
        "gguf"
        if doc.edge_model.lower() in ("gguf", "auto") and st["gguf_ready"]
        else "builtin"
    )
    return st
