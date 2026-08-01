#!/usr/bin/env python3
"""Download default GGUF edge model and install llama-cpp-python."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp-server"
_VENV_PY = _MCP / ".venv" / "bin" / "python"

if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    os.execv(str(_VENV_PY), [str(_VENV_PY), __file__, *sys.argv[1:]])

from hui_mcp.agent.edge_gguf import (  # noqa: E402
    DEFAULT_MODEL_URL,
    EXPECTED_GGUF_BYTES,
    default_gguf_path,
    gguf_model_ready,
    gguf_runtime_available,
    validate_gguf_file,
)
from hui_mcp.config import AppConfig, DocReadConfig  # noqa: E402


def install_llama_cpp() -> None:
    print("→ pip install llama-cpp-python …")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "llama-cpp-python>=0.3.0"],
        cwd=str(_MCP),
    )


def download_model(dest: Path, url: str, *, max_retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"→ download {url}")
    print(f"  → {dest}")

    import shutil
    import subprocess

    if shutil.which("curl"):
        for attempt in range(1, max_retries + 1):
            cmd = [
                "curl",
                "-L",
                "--fail",
                "--retry",
                "5",
                "--retry-delay",
                "2",
                "-C",
                "-",
                "-o",
                str(tmp),
                url,
            ]
            print(f"  curl attempt {attempt}/{max_retries} …")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and tmp.is_file():
                ok, reason = validate_gguf_file(tmp)
                if ok:
                    tmp.replace(dest)
                    print(f"✓ saved {dest} ({dest.stat().st_size // (1024 * 1024)}MB)")
                    return
                print(f"  invalid after download: {reason}")
            elif proc.stderr.strip():
                print(f"  curl: {proc.stderr.strip()[:200]}")
            if attempt < max_retries:
                print("  retrying…")
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise RuntimeError("curl download failed after retries")

    if tmp.is_file():
        tmp.unlink(missing_ok=True)
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            _urllib_download_model(dest, url, tmp)
            return
        except Exception as e:
            last_err = e
            print(f"  urllib attempt {attempt}/{max_retries} failed: {e}")
    raise RuntimeError(f"download failed: {last_err}")


def _urllib_download_model(dest: Path, url: str, tmp: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        chunk = 1024 * 256
        with tmp.open("wb") as f:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if total:
                    pct = done * 100 // total
                    print(f"\r  {pct}% ({done // (1024 * 1024)}MB)", end="", flush=True)
    print()
    if total and done != total:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download incomplete: {done}/{total} bytes")
    ok, reason = validate_gguf_file(tmp)
    if not ok:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file invalid: {reason}")
    tmp.replace(dest)
    print(f"✓ saved {dest} ({dest.stat().st_size // (1024 * 1024)}MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup local GGUF edge model")
    parser.add_argument("--url", default=DEFAULT_MODEL_URL, help="GGUF download URL")
    parser.add_argument("--dest", default="", help="Output .gguf path")
    parser.add_argument("--skip-pip", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a file exists (use when model is corrupt/incomplete)",
    )
    args = parser.parse_args()

    dest = Path(args.dest).expanduser() if args.dest else default_gguf_path()

    if not args.skip_pip and not gguf_runtime_available():
        install_llama_cpp()

    if dest.is_file():
        ok, reason = validate_gguf_file(dest)
        if ok and not args.force:
            print(f"✓ model already exists: {dest}")
        elif args.force or not ok:
            if not ok:
                print(f"⚠ existing model invalid ({reason}), re-downloading…")
            else:
                print("→ --force: re-downloading model…")
            dest.unlink(missing_ok=True)

    if not args.skip_download and not validate_gguf_file(dest)[0]:
        download_model(dest, args.url)
    elif validate_gguf_file(dest)[0]:
        print(f"✓ model ready: {dest} (~{dest.stat().st_size // (1024 * 1024)}MB)")

    cfg = AppConfig.load()
    cfg.doc_read.edge_model = "auto"
    if args.dest:
        cfg.doc_read.gguf_model_path = str(dest)
    elif not cfg.doc_read.gguf_model_path:
        cfg.doc_read.gguf_model_path = str(dest)
    cfg.save()
    print("✓ config updated: doc_read.edge_model=auto")
    print(f"  gguf_model_path={cfg.doc_read.gguf_model_path or dest}")
    print(f"  expected_size≈{EXPECTED_GGUF_BYTES // (1024 * 1024)}MB")

    doc = DocReadConfig(gguf_model_path=str(dest))
    if gguf_model_ready(doc):
        print("✓ GGUF edge model ready")
        return 0
    ok, reason = validate_gguf_file(dest)
    print(f"⚠ GGUF not ready — {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
