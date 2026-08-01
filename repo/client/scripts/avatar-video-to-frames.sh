#!/usr/bin/env bash
# Extract PNG sequence from a portrait / talking-head video.
# Usage: ./scripts/avatar-video-to-frames.sh <input.mp4> <output_dir> [fps=12]
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg required (brew install ffmpeg)" >&2
  exit 1
fi

INPUT="${1:?input video path}"
OUT="${2:?output directory, e.g. ui/public/avatar/seq/speaking}"
FPS="${3:-12}"

mkdir -p "$OUT"
rm -f "$OUT"/frame_*.png

ffmpeg -y -i "$INPUT" -vf "fps=${FPS},scale=104:118:force_original_aspect_ratio=increase,crop=104:118" \
  "$OUT/frame_%04d.png"

COUNT="$(ls -1 "$OUT"/frame_*.png 2>/dev/null | wc -l | tr -d ' ')"
echo "[avatar] wrote ${COUNT} frames -> ${OUT} @ ${FPS}fps"
echo "Update ui/public/avatar/manifest.json count/fps for this sequence."
