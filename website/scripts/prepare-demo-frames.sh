#!/usr/bin/env bash
# Build website demo frames from Companion seq-webp (same assets as desktop app).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEQ="$ROOT/../repo/client/ui/public/avatar/seq-webp"
OUT="$ROOT/assets/avatar"
# 2× Companion display (104×141 → 208×282 canvas)
WIDTH="${1:-208}"
QUALITY="${2:-88}"

if ! command -v cwebp >/dev/null; then
  echo "error: cwebp not found (brew install webp)"
  exit 1
fi

compress_one() {
  local src="$1" dst="$2"
  cwebp -q "$QUALITY" -resize "$WIDTH" 0 "$src" -o "$dst" >/dev/null 2>&1
}

copy_seq_frame() {
  local seq="$1" frame="$2" out_dir="$3" out_name="$4"
  local src="$SEQ/$seq/frame_$(printf '%04d' "$frame").webp"
  if [ ! -f "$src" ]; then
    echo "error: missing $src"
    exit 1
  fi
  mkdir -p "$out_dir"
  compress_one "$src" "$out_dir/$out_name"
}

sample_speaking() {
  local out_dir="$1" step="$2" max="$3"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  local n=0 i=1
  while (( n < max )); do
    local src="$SEQ/speaking/frame_$(printf '%04d' "$i").webp"
    if [ ! -f "$src" ]; then break; fi
    n=$((n + 1))
    compress_one "$src" "$out_dir/frame_$(printf '%04d' "$n").webp"
    i=$((i + step))
  done
  echo "$n"
}

rm -rf "$OUT/idle" "$OUT/listening" "$OUT/speaking"
mkdir -p "$OUT"

# Match Companion: idle / listening are single-frame holds (seq-webp only ships frame_0001).
copy_seq_frame idle 1 "$OUT/idle" "frame_0001.webp"
copy_seq_frame listening 1 "$OUT/listening" "frame_0001.webp"
SPEAK_N=$(sample_speaking "$OUT/speaking" 8 24)

cat > "$OUT/manifest.json" <<EOF
{
  "version": 1,
  "width": 1800,
  "height": 2435,
  "sequences": {
    "idle": {
      "dir": "assets/avatar/idle",
      "pattern": "frame_%04d.webp",
      "count": 1,
      "fps": 8
    },
    "listening": {
      "dir": "assets/avatar/listening",
      "pattern": "frame_%04d.webp",
      "count": 1,
      "fps": 6
    },
    "speaking": {
      "dir": "assets/avatar/speaking",
      "pattern": "frame_%04d.webp",
      "count": ${SPEAK_N},
      "fps": 12
    }
  },
  "modeMap": {
    "idle": "idle",
    "listening": "listening",
    "speaking": "speaking"
  }
}
EOF

echo "idle: 1  listening: 1  speaking: ${SPEAK_N}"
echo "source: $SEQ"
echo "done -> $OUT ($(du -sh "$OUT" | awk '{print $1}'))"
