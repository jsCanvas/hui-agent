#!/usr/bin/env bash
# Website demo loops — ONLY seq-webp/greetings (same character as frame_0001).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/../repo/client/ui/public/avatar/seq-webp/greetings"
OUT="$ROOT/assets/avatar"
WIDTH="${1:-208}"
QUALITY="${2:-86}"

if ! command -v cwebp >/dev/null; then
  echo "error: cwebp not found (brew install webp)"
  exit 1
fi

if [ ! -d "$SRC" ] || [ ! -f "$SRC/frame_0001.webp" ]; then
  echo "error: missing $SRC/frame_0001.webp"
  exit 1
fi

compress_frame() {
  cwebp -q "$QUALITY" -resize "$WIDTH" 0 "$1" -o "$2" >/dev/null 2>&1
}

# sample_segment out_dir start step max — all from greetings HD webp
sample_segment() {
  local out_dir="$1" start="$2" step="$3" max="$4"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  local n=0 i="$start"
  while (( n < max )); do
    printf -v num "%04d" "$i"
    local src="$SRC/frame_${num}.webp"
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

rm -rf "$OUT/greetings" "$OUT/idle" "$OUT/listening" "$OUT/speaking"
mkdir -p "$OUT"

# Same HD character; different motion segments from greetings loop:
LISTEN_N=$(sample_segment "$OUT/listening" 1 3 14)
GREET_N=$(sample_segment "$OUT/greetings" 1 4 24)
IDLE_N=$(sample_segment "$OUT/idle" 1 8 12)
SPEAK_N=$(sample_segment "$OUT/speaking" 24 2 22)

cat > "$OUT/manifest.json" <<EOF
{
  "version": 1,
  "width": 1800,
  "height": 2435,
  "sequences": {
    "listening": {
      "dir": "assets/avatar/listening",
      "pattern": "frame_%04d.webp",
      "count": ${LISTEN_N},
      "fps": 6
    },
    "greetings": {
      "dir": "assets/avatar/greetings",
      "pattern": "frame_%04d.webp",
      "count": ${GREET_N},
      "fps": 12
    },
    "idle": {
      "dir": "assets/avatar/idle",
      "pattern": "frame_%04d.webp",
      "count": ${IDLE_N},
      "fps": 8
    },
    "speaking": {
      "dir": "assets/avatar/speaking",
      "pattern": "frame_%04d.webp",
      "count": ${SPEAK_N},
      "fps": 12
    }
  },
  "stepMap": ["listening", "greetings", "idle", "idle", "speaking"]
}
EOF

echo "listening:${LISTEN_N} greetings:${GREET_N} idle:${IDLE_N} speaking:${SPEAK_N}"
echo "source: $SRC (greetings/frame_0001 character only)"
echo "done -> $OUT ($(du -sh "$OUT" | awk '{print $1}'))"
