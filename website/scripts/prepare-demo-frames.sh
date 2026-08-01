#!/usr/bin/env bash
# Copy Companion listening portrait verbatim (no re-encode).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/../repo/client/ui/public/avatar/seq-webp/listening/frame_0001.webp"
OUT="$ROOT/assets/avatar/portrait.webp"

if [ ! -f "$SRC" ]; then
  echo "error: missing $SRC"
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp -f "$SRC" "$OUT"

cat > "$ROOT/assets/avatar/manifest.json" <<EOF
{
  "version": 1,
  "width": 1800,
  "height": 2435,
  "portrait": "assets/avatar/portrait.webp"
}
EOF

echo "copied $(basename "$SRC") -> $OUT ($(du -h "$OUT" | awk '{print $1}'))"
