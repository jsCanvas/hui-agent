#!/usr/bin/env python3
"""Build default portrait frame sequences from base image (or synth until real video is added)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
except ImportError:
    print("error: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "ui" / "public" / "avatar"
BASE = PUBLIC / "companion-portrait.png"
MANIFEST = PUBLIC / "manifest.json"


def ensure_base() -> Image.Image:
    if not BASE.is_file():
        raise SystemExit(f"missing base portrait: {BASE}")
    return Image.open(BASE).convert("RGBA").resize((104, 118), Image.Resampling.LANCZOS)


def save_seq(frames: list[Image.Image], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.png"):
        old.unlink()
    for i, frame in enumerate(frames, start=1):
        frame.save(out_dir / f"frame_{i:04d}.png", optimize=True)


def build_idle(base: Image.Image, count: int = 16) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for i in range(count):
        t = i / max(1, count - 1)
        pulse = 1.0 + 0.012 * math.sin(t * math.pi * 2)
        w, h = base.size
        nw, nh = int(w * pulse), int(h * pulse)
        scaled = base.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ox = (base.width - nw) // 2
        oy = (base.height - nh) // 2 - 2
        canvas.paste(scaled, (ox, oy), scaled)
        frames.append(canvas)
    return frames


def build_listening(base: Image.Image, count: int = 12) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for i in range(count):
        t = i / max(1, count - 1)
        glow = 1.0 + 0.06 * math.sin(t * math.pi * 2)
        img = ImageEnhance.Brightness(base).enhance(glow)
        overlay = Image.new("RGBA", base.size, (52, 211, 153, int(18 + 10 * math.sin(t * math.pi * 2))))
        out = Image.alpha_composite(img, overlay)
        frames.append(out)
    return frames


def build_speaking(base: Image.Image, count: int = 24) -> list[Image.Image]:
    frames: list[Image.Image] = []
    cx = base.width * 0.5
    mouth_y = base.height * 0.715
    for i in range(count):
        t = i / max(1, count - 1)
        open_level = max(0.0, math.sin(t * math.pi) ** 0.85)
        frame = base.copy()
        draw = ImageDraw.Draw(frame)
        rx = 5 + open_level * 7
        ry = 2 + open_level * 10
        draw.ellipse(
            (cx - rx, mouth_y - ry, cx + rx, mouth_y + ry),
            fill=(55, 18, 28, int(160 + open_level * 80)),
        )
        if open_level > 0.15:
            frame = frame.filter(ImageFilter.GaussianBlur(radius=0.3))
        frames.append(frame)
    return frames


def main() -> int:
    base = ensure_base()
    seq_root = PUBLIC / "seq"

    idle = build_idle(base, 16)
    listening = build_listening(base, 12)
    speaking = build_speaking(base, 24)

    save_seq(idle, seq_root / "idle")
    save_seq(listening, seq_root / "listening")
    save_seq(speaking, seq_root / "speaking")

    if MANIFEST.is_file():
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        data["sequences"]["idle"]["count"] = len(idle)
        data["sequences"]["listening"]["count"] = len(listening)
        data["sequences"]["speaking"]["count"] = len(speaking)
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[avatar] built sequences -> {seq_root}")
    print("  idle:", len(idle), "listening:", len(listening), "speaking:", len(speaking))
    print("Replace with real video frames: ./scripts/avatar-video-to-frames.sh talk.mp4 ui/public/avatar/seq/speaking 12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
