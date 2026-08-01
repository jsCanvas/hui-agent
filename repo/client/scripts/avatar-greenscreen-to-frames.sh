#!/usr/bin/env bash
# Extract PNG sequence from green-screen portrait video with chroma key.
# Usage:
#   ./scripts/avatar-greenscreen-to-frames.sh <input.mov> <output_dir> [fps=60] [key=0x00CC28] [full]
# Set "full" as 5th arg to keep source resolution (no scale/crop).
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg required (brew install ffmpeg)" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT="${1:?input video path}"
OUT="${2:?output directory, e.g. ui/public/avatar/seq/speaking}"
FPS="${3:-60}"
KEY="${4:-0x00CC28}"
FULL="${5:-}"

MANIFEST="${ROOT}/ui/public/avatar/manifest.json"

read -r SRC_DIM <<<"$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height -of csv=p=0:s=x "$INPUT")"
SRC_W="${SRC_DIM%x*}"
SRC_H="${SRC_DIM#*x}"

if [[ "$FULL" == "full" || "$FULL" == "1" || "$FULL" == "true" ]]; then
  VF="fps=${FPS},chromakey=${KEY}:0.22:0.06,format=rgba"
  OUT_W="$SRC_W"
  OUT_H="$SRC_H"
  echo "[avatar] full resolution ${OUT_W}x${OUT_H}"
else
  VF="fps=${FPS},chromakey=${KEY}:0.22:0.06,scale=104:118:force_original_aspect_ratio=increase,crop=104:118,format=rgba"
  OUT_W=104
  OUT_H=118
  echo "[avatar] companion size ${OUT_W}x${OUT_H}"
fi

mkdir -p "$OUT"
rm -f "$OUT"/frame_*.png

ffmpeg -y -i "$INPUT" -vf "$VF" -pix_fmt rgba "$OUT/frame_%04d.png"

COUNT="$(ls -1 "$OUT"/frame_*.png 2>/dev/null | wc -l | tr -d ' ')"
SEQ_NAME="$(basename "$OUT")"
echo "[avatar] keyed ${COUNT} frames -> ${OUT} @ ${FPS}fps (key ${KEY})"

if [[ -f "$MANIFEST" ]] && command -v python3 >/dev/null 2>&1; then
  MANIFEST="$MANIFEST" COUNT="$COUNT" FPS="$FPS" OUT_W="$OUT_W" OUT_H="$OUT_H" SEQ_NAME="$SEQ_NAME" python3 - <<'PY'
import json
import os
from pathlib import Path

p = Path(os.environ["MANIFEST"])
count = int(os.environ["COUNT"])
fps = int(os.environ["FPS"])
w = int(os.environ["OUT_W"])
h = int(os.environ["OUT_H"])
seq = os.environ["SEQ_NAME"]
data = json.loads(p.read_text(encoding="utf-8"))
data["width"] = w
data["height"] = h
if seq not in data.get("sequences", {}):
    raise SystemExit(f"unknown sequence in manifest: {seq}")
data["sequences"][seq] = {
    "dir": f"/avatar/seq/{seq}",
    "pattern": "frame_%04d.png",
    "count": count,
    "fps": fps,
    "width": w,
    "height": h,
}
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[avatar] manifest {seq} -> {w}x{h} count={count} fps={fps}")
PY
fi
