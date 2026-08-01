#!/usr/bin/env python3
"""Generate minimal Tauri icon set."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"
ROOT.mkdir(parents=True, exist_ok=True)


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, size: int, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    # Tauri requires RGBA PNG
    raw = b"".join(b"\x00" + bytes([r, g, b, 255]) * size for _ in range(size))
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", ihdr)
    png += png_chunk(b"IDAT", compressed)
    png += png_chunk(b"IEND", b"")
    path.write_bytes(png)


color = (251, 113, 133)  # rose-400
write_png(ROOT / "32x32.png", 32, color)
write_png(ROOT / "128x128.png", 128, color)
write_png(ROOT / "128x128@2x.png", 256, color)
# icns/ico: tauri build can generate from png on mac; copy png as fallback names
(ROOT / "icon.png").write_bytes((ROOT / "128x128.png").read_bytes())
print("icons written to", ROOT)
