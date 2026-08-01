#!/usr/bin/env python3
"""Generate idle / listening / speaking portrait videos and PNG sequences for Companion avatar."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
except ImportError:
    print("error: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "ui" / "public" / "avatar"
SOURCE = PUBLIC / "source-portrait.png"
PORTRAIT = PUBLIC / "companion-portrait.png"
MANIFEST = PUBLIC / "manifest.json"
VIDEO_DIR = PUBLIC / "video"
SEQ_ROOT = PUBLIC / "seq"

OUT_W, OUT_H = 104, 118
WORK_W, WORK_H = OUT_W * 4, OUT_H * 4


@dataclass(frozen=True)
class FaceLayout:
    cx: float
    eye_y: float
    eye_rx: float
    eye_ry: float
    eye_gap: float
    mouth_y: float
    mouth_rx: float
    mouth_ry: float


LAYOUT = FaceLayout(
    cx=WORK_W * 0.5,
    eye_y=WORK_H * 0.38,
    eye_rx=WORK_W * 0.055,
    eye_ry=WORK_H * 0.028,
    eye_gap=WORK_W * 0.11,
    mouth_y=WORK_H * 0.72,
    mouth_rx=WORK_W * 0.09,
    mouth_ry=WORK_H * 0.035,
)


BG_EDGE_THRESHOLD = 26.0


def _color_dist(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _edge_bg_refs(img: Image.Image) -> list[tuple[int, int, int]]:
    px = img.load()
    w, h = img.size
    refs: list[tuple[int, int, int]] = []
    step_x = max(1, w // 32)
    step_y = max(1, h // 32)
    for x in range(0, w, step_x):
        refs.append(px[x, 0][:3])
        refs.append(px[x, h - 1][:3])
    for y in range(0, h, step_y):
        refs.append(px[0, y][:3])
        refs.append(px[w - 1, y][:3])
    return refs


def _is_bg_color(rgb: tuple[int, int, int], refs: list[tuple[int, int, int]], threshold: float) -> bool:
    return min(_color_dist(rgb, ref) for ref in refs) <= threshold


def remove_background(img: Image.Image, threshold: float = BG_EDGE_THRESHOLD) -> Image.Image:
    """Remove backdrop while preserving the portrait (edge color match + center guard)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    refs = _edge_bg_refs(rgba)

    cx, cy = w * 0.5, h * 0.42
    guard_rx, guard_ry = w * 0.34, h * 0.42

    alpha = Image.new("L", (w, h), 0)
    alpha_px = alpha.load()
    for y in range(h):
        for x in range(w):
            in_guard = ((x - cx) / guard_rx) ** 2 + ((y - cy) / guard_ry) ** 2 <= 1.0
            if in_guard or not _is_bg_color(px[x, y][:3], refs, threshold):
                alpha_px[x, y] = 255

    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.4))
    rgba.putalpha(alpha)
    return rgba


def load_portrait() -> Image.Image:
    src = SOURCE if SOURCE.is_file() else PORTRAIT
    if not src.is_file():
        raise SystemExit(f"missing portrait: {SOURCE} or {PORTRAIT}")
    img = Image.open(src).convert("RGBA")
    alpha_lo, _alpha_hi = img.getextrema()[3]
    if alpha_lo > 240:
        img = remove_background(img)
    scale = max(WORK_W / img.width, WORK_H / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - WORK_W) // 2
    top = max(0, (nh - WORK_H) // 2 - int(WORK_H * 0.04))
    img = img.crop((left, top, left + WORK_W, top + WORK_H))
    return img


def downscale(frame: Image.Image) -> Image.Image:
    return frame.resize((OUT_W, OUT_H), Image.Resampling.LANCZOS)


def save_portrait_thumb(base: Image.Image) -> None:
    downscale(base).save(PORTRAIT, optimize=True)


def apply_breath(base: Image.Image, amount: float) -> Image.Image:
    pulse = 1.0 + 0.018 * amount
    w, h = base.size
    nw, nh = int(w * pulse), int(h * pulse)
    scaled = base.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ox = (w - nw) // 2
    oy = (h - nh) // 2 - int(2 * amount)
    canvas.paste(scaled, (ox, oy), scaled)
    return canvas


def apply_head_tilt(base: Image.Image, angle_deg: float, dy: float = 0.0) -> Image.Image:
    rotated = base.rotate(
        angle_deg,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )
    if abs(dy) < 0.5:
        return rotated
    canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    canvas.paste(rotated, (0, int(dy)), rotated)
    return canvas


def draw_blink(base: Image.Image, strength: float) -> Image.Image:
    if strength <= 0.01:
        return base
    frame = base.copy()
    draw = ImageDraw.Draw(frame)
    for sign in (-1, 1):
        ex = LAYOUT.cx + sign * LAYOUT.eye_gap * 0.5
        ey = LAYOUT.eye_y
        lid_h = LAYOUT.eye_ry * 2.2 * strength
        draw.ellipse(
            (ex - LAYOUT.eye_rx, ey - LAYOUT.eye_ry, ex + LAYOUT.eye_rx, ey - LAYOUT.eye_ry + lid_h),
            fill=(28, 22, 20, int(210 * strength)),
        )
    return frame


def warp_mouth(base: Image.Image, open_level: float, smile: float = 0.0) -> Image.Image:
    """Simulate lip motion by stretching a mouth patch vertically."""
    level = max(0.0, min(1.0, open_level))
    frame = base.copy()
    if level < 0.03 and smile < 0.03:
        return frame

    mx = int(LAYOUT.cx - LAYOUT.mouth_rx)
    my = int(LAYOUT.mouth_y - LAYOUT.mouth_ry * 1.2)
    mw = int(LAYOUT.mouth_rx * 2)
    mh = int(LAYOUT.mouth_ry * 2.4)
    patch = base.crop((mx, my, mx + mw, my + mh))

    stretch_y = 1.0 + level * 0.55 + smile * 0.12
    stretch_x = 1.0 + level * 0.08 + smile * 0.06
    new_w = max(1, int(mw * stretch_x))
    new_h = max(1, int(mh * stretch_y))
    warped = patch.resize((new_w, new_h), Image.Resampling.LANCZOS)

    paste_x = mx - (new_w - mw) // 2
    paste_y = my - int((new_h - mh) * 0.35)
    frame.paste(warped, (paste_x, paste_y), warped)

    if level > 0.12:
        draw = ImageDraw.Draw(frame)
        inner_rx = LAYOUT.mouth_rx * (0.35 + level * 0.45)
        inner_ry = LAYOUT.mouth_ry * (0.25 + level * 0.85)
        draw.ellipse(
            (
                LAYOUT.cx - inner_rx,
                LAYOUT.mouth_y - inner_ry * 0.4,
                LAYOUT.cx + inner_rx,
                LAYOUT.mouth_y + inner_ry,
            ),
            fill=(48, 16, 22, int(120 + level * 100)),
        )
    return frame.filter(ImageFilter.GaussianBlur(radius=0.15))


def build_idle_frames(base: Image.Image, count: int = 24) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for i in range(count):
        t = i / count
        breath = math.sin(t * math.pi * 2)
        tilt = 0.35 * math.sin(t * math.pi * 2 + 0.6)
        blink = max(0.0, math.sin(t * math.pi * 2 * 0.5 - 1.2) ** 8)
        img = apply_breath(base, breath)
        img = apply_head_tilt(img, tilt, dy=math.sin(t * math.pi * 2) * 1.2)
        img = draw_blink(img, blink)
        frames.append(downscale(img))
    return frames


def build_listening_frames(base: Image.Image, count: int = 18) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for i in range(count):
        t = i / count
        attentive = 0.5 + 0.5 * math.sin(t * math.pi * 2)
        img = apply_breath(base, 0.4 * attentive)
        img = apply_head_tilt(img, 0.8 * math.sin(t * math.pi * 2 + 0.3), dy=-1.5)
        img = warp_mouth(img, open_level=0.05, smile=0.25 + 0.15 * attentive)
        glow = ImageEnhance.Brightness(img).enhance(1.03 + 0.04 * attentive)
        overlay = Image.new("RGBA", glow.size, (80, 220, 180, 0))
        overlay_px = overlay.load()
        glow_px = glow.load()
        for y in range(glow.height):
            for x in range(glow.width):
                if glow_px[x, y][3] > 16:
                    overlay_px[x, y] = (80, 220, 180, int(12 + 14 * attentive))
        img = Image.alpha_composite(glow, overlay)
        frames.append(downscale(img))
    return frames


def build_speaking_frames(base: Image.Image, count: int = 36) -> list[Image.Image]:
    frames: list[Image.Image] = []
    # Viseme-like open pattern (closed -> open -> closed), loopable
    pattern = [0.05, 0.25, 0.55, 0.85, 0.65, 0.35, 0.15, 0.45, 0.75, 0.4, 0.1, 0.3]
    for i in range(count):
        t = i / count
        idx = int(t * len(pattern)) % len(pattern)
        nxt = (idx + 1) % len(pattern)
        frac = (t * len(pattern)) % 1.0
        open_level = pattern[idx] * (1 - frac) + pattern[nxt] * frac
        img = apply_breath(base, 0.25 + open_level * 0.2)
        img = apply_head_tilt(img, 0.2 * math.sin(t * math.pi * 4), dy=open_level * 1.5)
        img = warp_mouth(img, open_level=open_level, smile=0.05)
        frames.append(downscale(img))
    return frames


def save_sequence(frames: list[Image.Image], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.png"):
        old.unlink()
    for i, frame in enumerate(frames, start=1):
        frame.save(out_dir / f"frame_{i:04d}.png", optimize=True)


def encode_mp4(frames: list[Image.Image], out_path: Path, fps: int) -> None:
    if not shutil.which("ffmpeg"):
        print("warn: ffmpeg not found, skip mp4", file=sys.stderr)
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avatar-vid-") as tmp:
        tmp_dir = Path(tmp)
        for i, frame in enumerate(frames, start=1):
            frame.save(tmp_dir / f"frame_{i:04d}.png")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(tmp_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def update_manifest(idle_n: int, listen_n: int, speak_n: int) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {
        "version": 1,
        "width": OUT_W,
        "height": OUT_H,
        "sequences": {},
        "modeMap": {
            "resting": "idle",
            "conversation": "idle",
            "waiting": "idle",
            "executing": "idle",
            "completed": "idle",
            "listening": "listening",
            "speaking": "speaking",
        },
    }
    data["width"] = OUT_W
    data["height"] = OUT_H
    data["sequences"]["idle"] = {
        "dir": "/avatar/seq/idle",
        "pattern": "frame_%04d.png",
        "count": idle_n,
        "fps": 8,
    }
    data["sequences"]["listening"] = {
        "dir": "/avatar/seq/listening",
        "pattern": "frame_%04d.png",
        "count": listen_n,
        "fps": 6,
    }
    data["sequences"]["speaking"] = {
        "dir": "/avatar/seq/speaking",
        "pattern": "frame_%04d.png",
        "count": speak_n,
        "fps": 12,
    }
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    base = load_portrait()
    save_portrait_thumb(base)

    idle = build_idle_frames(base, 24)
    listening = build_listening_frames(base, 18)
    speaking = build_speaking_frames(base, 36)

    save_sequence(idle, SEQ_ROOT / "idle")
    save_sequence(listening, SEQ_ROOT / "listening")
    save_sequence(speaking, SEQ_ROOT / "speaking")

    encode_mp4(idle, VIDEO_DIR / "idle.mp4", fps=8)
    encode_mp4(listening, VIDEO_DIR / "listening.mp4", fps=6)
    encode_mp4(speaking, VIDEO_DIR / "speaking.mp4", fps=12)

    update_manifest(len(idle), len(listening), len(speaking))

    print(f"[avatar] portrait -> {PORTRAIT}")
    print(f"[avatar] videos -> {VIDEO_DIR}")
    print(f"[avatar] sequences -> {SEQ_ROOT}")
    print(f"  idle={len(idle)} listening={len(listening)} speaking={len(speaking)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
