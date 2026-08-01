"""Local GGUF edge inference via llama-cpp-python (optional dependency)."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hui_mcp.config import DocReadConfig

log = logging.getLogger("hui_mcp.edge_gguf")

DEFAULT_MODEL_NAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
# Qwen2.5-0.5B-Instruct Q4_K_M on HuggingFace (bytes)
EXPECTED_GGUF_BYTES = 491_400_032
MIN_GGUF_BYTES = 450_000_000

_llama: Any | None = None
_llama_path: str | None = None
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


def default_gguf_path() -> Path:
    home = Path(os.environ.get("HUI_AGENT_HOME", Path.home() / ".hui-agent"))
    return home / "models" / DEFAULT_MODEL_NAME


def resolve_gguf_path(cfg: DocReadConfig) -> Path:
    raw = (cfg.gguf_model_path or os.environ.get("HUI_AGENT_GGUF_MODEL", "")).strip()
    if raw:
        p = Path(raw).expanduser()
        return p
    return default_gguf_path()


def gguf_runtime_available() -> bool:
    try:
        import llama_cpp  # noqa: F401

        return True
    except ImportError:
        return False


def validate_gguf_file(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "file missing"
    size = path.stat().st_size
    if size < MIN_GGUF_BYTES:
        return False, f"incomplete ({size // (1024 * 1024)}MB, need ~{EXPECTED_GGUF_BYTES // (1024 * 1024)}MB)"
    if path.read_bytes()[:4] != b"GGUF":
        return False, "not a GGUF file"
    return True, "ok"


def gguf_model_ready(cfg: DocReadConfig) -> bool:
    if not gguf_runtime_available():
        return False
    path = resolve_gguf_path(cfg)
    ok, _reason = validate_gguf_file(path)
    return ok


def gguf_status(cfg: DocReadConfig) -> dict[str, Any]:
    path = resolve_gguf_path(cfg)
    valid, reason = validate_gguf_file(path) if path.is_file() else (False, "file missing")
    size = path.stat().st_size if path.is_file() else 0
    return {
        "runtime": gguf_runtime_available(),
        "model_path": str(path),
        "model_exists": path.is_file(),
        "model_bytes": size,
        "expected_bytes": EXPECTED_GGUF_BYTES,
        "model_valid": valid,
        "model_issue": None if valid else reason,
        "loaded": _llama is not None,
        "default_download": DEFAULT_MODEL_URL,
    }


def _thread_count(cfg: DocReadConfig) -> int:
    n = int(cfg.gguf_n_threads or 0)
    if n > 0:
        return n
    cpus = os.cpu_count() or 4
    return max(1, min(cpus - 1, 8))


def _load_llama(cfg: DocReadConfig):
    global _llama, _llama_path
    from llama_cpp import Llama

    path = resolve_gguf_path(cfg)
    ok, reason = validate_gguf_file(path)
    if not ok:
        raise FileNotFoundError(f"GGUF model invalid: {path} ({reason})")

    path_str = str(path.resolve())
    with _load_lock:
        if _llama is not None and _llama_path == path_str:
            return _llama
        log.info("loading GGUF edge model: %s", path_str)
        _llama = Llama(
            model_path=path_str,
            n_ctx=int(cfg.gguf_n_ctx),
            n_threads=_thread_count(cfg),
            n_gpu_layers=int(cfg.gguf_n_gpu_layers),
            verbose=False,
        )
        _llama_path = path_str
        return _llama


def build_gguf_outline(
    section: str,
    ocr_text: str,
    cfg: DocReadConfig,
    *,
    max_chars: int = 6000,
) -> str:
    """Summarize OCR text with a local GGUF model."""
    text = (ocr_text or "").strip()
    if len(text) < 40:
        return ""

    llm = _load_llama(cfg)
    excerpt = text[: int(cfg.gguf_input_chars)]
    system = (
        "你是文档结构化助手。根据 OCR 原文提取章节要点、流程步骤、字段/API 名称。"
        "输出简洁中文 Markdown 大纲，只写原文中出现的内容，不要编造。"
    )
    user = f"章节：{section}\n\nOCR 原文：\n{excerpt}"

    with _infer_lock:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=float(cfg.gguf_temperature),
            max_tokens=int(cfg.gguf_max_tokens),
        )
    content = (
        ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    if not content:
        return ""
    header = f"## {section} — GGUF 本地大纲\n\n"
    body = header + content
    if len(body) > max_chars:
        body = body[: max_chars - 20] + "\n\n…（大纲已截断）"
    return body


def unload_gguf() -> None:
    global _llama, _llama_path
    with _load_lock:
        _llama = None
        _llama_path = None


def plan_voice_duplex_gguf(text: str, cfg: DocReadConfig) -> dict[str, Any] | None:
    """Optional GGUF: instant ack + speak segment list (JSON-ish)."""
    text = (text or "").strip()
    if len(text) < 2 or not gguf_model_ready(cfg):
        return None

    llm = _load_llama(cfg)
    system = (
        "你是语音助手小绘的边缘规划器。根据用户一句话，输出 JSON 对象，字段："
        "ack_text（一句即时中文回复）、speak_segments（2-3 句中文口播数组）。"
        "只输出 JSON，不要 markdown。"
    )
    user = f"用户说：{text[:400]}"

    with _infer_lock:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=256,
        )
    content = (
        ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    if not content:
        return None
    try:
        import json

        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content.strip())
        if isinstance(data, dict) and data.get("ack_text"):
            return data
    except (json.JSONDecodeError, ValueError):
        return {"ack_text": content[:120], "speak_segments": [content[:120]]}
    return None
