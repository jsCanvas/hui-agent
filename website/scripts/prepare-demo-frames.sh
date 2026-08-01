#!/usr/bin/env bash
# Build lightweight WebP demo loops from Companion HD portrait seq-webp (white-outline character).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AVATAR="$ROOT/../repo/client/ui/public/avatar/seq-webp"
OUT="$ROOT/assets/avatar"
WIDTH="${1:-160}"
QUALITY="${2:-82}"

if ! command -v cwebp >/dev/null; then
  echo "error: cwebp not found (brew install webp)"
  exit 1
fi

compress_frame() {
  local src="$1" dst="$2"
  cwebp -q "$QUALITY" -resize "$WIDTH" 0 "$src" -o "$dst" >/dev/null 2>&1
}

sample_seq() {
  local src_dir="$1" out_dir="$2" step="$3" max="$4"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  local i=0 n=0
  for f in "$src_dir"/frame_*.webp; do
    [ -e "$f" ] || continue
    i=$((i + 1))
    if (( (i - 1) % step != 0 )); then continue; fi
    n=$((n + 1))
    printf -v idx "%04d" "$n"
    compress_frame "$f" "$out_dir/frame_${idx}.webp"
    if (( n >= max )); then break; fi
  done
  echo "$n"
}

rm -rf "$OUT/idle" "$OUT/listening" "$OUT/speaking"
mkdir -p "$OUT/idle" "$OUT/listening" "$OUT/speaking"

# HD portrait loops (same character as Companion seq-webp)
IDLE_N=$(sample_seq "$AVATAR/greetings" "$OUT/idle" 13 16)
LISTEN_N=$(sample_seq "$AVATAR/greetings" "$OUT/listening" 17 12)
SPEAK_N=$(sample_seq "$AVATAR/speaking" "$OUT/speaking" 9 20)

# Fallback if greetings incomplete
if (( IDLE_N < 4 )); then
  IDLE_N=$(sample_seq "$AVATAR/speaking" "$OUT/idle" 11 16)
fi
if (( LISTEN_N < 4 )); then
  LISTEN_N=$(sample_seq "$AVATAR/speaking" "$OUT/listening" 15 12)
fi

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
      "fps": 10
    }
  }
}
EOF

echo "idle: $IDLE_N  listening: $LISTEN_N  speaking: $SPEAK_N"
echo "done -> $OUT ($(du -sh "$OUT" | awk '{print $1}'))"
