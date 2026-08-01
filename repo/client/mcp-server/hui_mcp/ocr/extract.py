"""OCR text extraction from screenshots (optional tesseract)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("hui_mcp.ocr")

_TESSERACT = shutil.which("tesseract")


def ocr_image(path: str | Path, *, lang: str = "chi_sim+eng") -> str:
    """Return OCR text for an image, or empty string if unavailable."""
    p = Path(path)
    if not p.is_file():
        return ""
    if not _TESSERACT:
        return ""
    try:
        proc = subprocess.run(
            [_TESSERACT, str(p), "stdout", "-l", lang, "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if proc.returncode != 0:
            log.debug("tesseract failed: %s", proc.stderr[:200])
            return ""
        return (proc.stdout or "").strip()
    except Exception as e:
        log.debug("ocr error: %s", e)
        return ""


def ocr_available() -> bool:
    return _TESSERACT is not None
