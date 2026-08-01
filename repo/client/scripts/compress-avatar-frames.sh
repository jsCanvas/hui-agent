#!/usr/bin/env bash
# Compress HD PNG avatar sequences to WebP for smaller bundle size.
# Usage: cd hui-agent/repo/client && bash scripts/compress-avatar-frames.sh [max_width] [quality]
# Defaults: max_width=1200, quality=85

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT/ui/public/avatar/seq"
OUT_DIR="$ROOT/ui/public/avatar/seq-webp"
MAX_WIDTH="${1:-1200}"
QUALITY="${2:-85}"

if ! command -v cwebp >/dev/null 2>&1; then
  echo "error: cwebp not found. Install with: brew install webp"
  exit 1
fi

mkdir -p "$OUT_DIR"

for seq in speaking greetings idle listening; do
  src="$SRC_DIR/$seq"
  dst="$OUT_DIR/$seq"
  if [ ! -d "$src" ]; then
    echo "skip: $src not found"
    continue
  fi
  mkdir -p "$dst"
  echo "compressing $seq -> $dst (width=${MAX_WIDTH}, quality=${QUALITY})"
  for f in "$src"/frame_*.png; do
    [ -e "$f" ] || continue
    name="$(basename "$f" .png).webp"
    cwebp -q "$QUALITY" -resize "$MAX_WIDTH" 0 "$f" -o "$dst/$name" >/dev/null 2>&1
  done
  echo "  done: $(ls "$dst"/*.webp 2>/dev/null | wc -l | awk '{print $1}') files"
done

# Print size comparison
echo ""
echo "size comparison:"
for seq in speaking greetings idle listening; do
  src="$SRC_DIR/$seq"
  dst="$OUT_DIR/$seq"
  [ -d "$src" ] || continue
  src_size=$(du -sh "$src" 2>/dev/null | awk '{print $1}')
  dst_size=$(du -sh "$dst" 2>/dev/null | awk '{print $1}')
  printf "  %-10s %8s -> %8s\n" "$seq" "$src_size" "$dst_size"
done
