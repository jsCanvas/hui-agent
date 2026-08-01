#!/usr/bin/env bash
# Extract lightweight WebP demo frames from Companion portrait videos for GitHub Pages.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEO="$ROOT/../repo/client/ui/public/avatar/video"
OUT="$ROOT/assets/avatar"

if ! command -v ffmpeg >/dev/null || ! command -v cwebp >/dev/null; then
  echo "error: need ffmpeg and cwebp (brew install ffmpeg webp)"
  exit 1
fi

for seq in idle listening speaking; do rm -rf "$OUT/$seq"; mkdir -p "$OUT/$seq"; done

ffmpeg -y -i "$VIDEO/idle.mp4" -vf "fps=8,scale=140:-1:flags=lanczos" -frames:v 16 "$OUT/idle/frame_%04d.png"
ffmpeg -y -i "$VIDEO/listening.mp4" -vf "fps=6,scale=140:-1:flags=lanczos" -frames:v 12 "$OUT/listening/frame_%04d.png"
ffmpeg -y -i "$VIDEO/speaking.mp4" -vf "fps=10,scale=140:-1:flags=lanczos" -frames:v 20 "$OUT/speaking/frame_%04d.png"

for seq in idle listening speaking; do
  for f in "$OUT/$seq"/*.png; do
    cwebp -q 82 "$f" -o "${f%.png}.webp" >/dev/null
    rm "$f"
  done
  echo "$seq: $(ls "$OUT/$seq" | wc -l | tr -d ' ') frames"
done

echo "done -> $OUT ($(du -sh "$OUT" | awk '{print $1}'))"
