#!/usr/bin/env bash
# Build website demo loops from HD portrait PNGs (same white-outline character as Companion speaking).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Full HD frames (182 speaking); fallback to seq-webp if beifen missing
SRC="${ROOT}/../repo/client/ui/public/avatar/beifen/speaking"
WEBP_SRC="${ROOT}/../repo/client/ui/public/avatar/seq-webp/speaking"
OUT="$ROOT/assets/avatar"
WIDTH="${1:-200}"
QUALITY="${2:-86}"

if ! command -v cwebp >/dev/null; then
  echo "error: cwebp not found (brew install webp)"
  exit 1
fi

compress_frame() {
  local src="$1" dst="$2"
  cwebp -q "$QUALITY" -resize "$WIDTH" 0 "$src" -o "$dst" >/dev/null 2>&1
}

# Sample numbered frames from source dir; output frame_0001..N.webp
sample_range() {
  local src_dir="$1" out_dir="$2" start="$3" step="$4" max="$5"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  local n=0 i="$start"
  while (( n < max )); do
    printf -v src_num "%04d" "$i"
    local src="$src_dir/frame_${src_num}.webp"
    if [ ! -f "$src" ]; then
      src="$src_dir/frame_${src_num}.png"
    fi
    if [ ! -f "$src" ]; then
      i=$((i + step))
      if (( i > start + step * max * 3 )); then break; fi
      continue
    fi
    n=$((n + 1))
    printf -v idx "%04d" "$n"
    compress_frame "$src" "$out_dir/frame_${idx}.webp"
    i=$((i + step))
  done
  echo "$n"
}

if [ ! -d "$SRC" ] || [ -z "$(ls -A "$SRC"/frame_*.png 2>/dev/null)" ]; then
  SRC="$WEBP_SRC"
  echo "note: using seq-webp/speaking (beifen PNG not found)"
fi

rm -rf "$OUT/idle" "$OUT/listening" "$OUT/speaking"
mkdir -p "$OUT/idle" "$OUT/listening" "$OUT/speaking"

# Same character, different motion segments from speaking loop:
# idle     — early frames, mouth mostly closed
# listening — mid-early frames, subtle head motion
# speaking  — full loop with mouth movement
IDLE_N=$(sample_range "$SRC" "$OUT/idle" 1 4 18)
LISTEN_N=$(sample_range "$SRC" "$OUT/listening" 3 3 14)
SPEAK_N=$(sample_range "$SRC" "$OUT/speaking" 1 9 22)

cat > "$OUT/manifest.json" <<EOF
{
  "version": 1,
  "width": 1800,
  "height": 2435,
  "sequences": {
    "idle": {
      "dir": "assets/avatar/idle",
      "pattern": "frame_%04d.webp",
      "count": ${IDLE_N},
      "fps": 8
    },
    "listening": {
      "dir": "assets/avatar/listening",
      "pattern": "frame_%04d.webp",
      "count": ${LISTEN_N},
      "fps": 6
    },
    "speaking": {
      "dir": "assets/avatar/speaking",
      "pattern": "frame_%04d.webp",
      "count": ${SPEAK_N},
      "fps": 12
    }
  }
}
EOF

echo "idle: $IDLE_N  listening: $LISTEN_N  speaking: $SPEAK_N"
echo "source: $SRC"
echo "done -> $OUT ($(du -sh "$OUT" | awk '{print $1}'))"
