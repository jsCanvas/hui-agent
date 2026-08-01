#!/usr/bin/env bash
# Download CC0 VRM avatar (MoonGirl from 100Avatars — stylized anime / 国漫风)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/ui/public/vrm/companion.vrm"
URL="${1:-https://arweave.net/m39XL2LTq_7B1kSjjfsiA_DDqFlfs0TOWjFZy-x8Grc}"

mkdir -p "$(dirname "$OUT")"
echo "[vrm] downloading MoonGirl (CC0) ..."
curl -fsSL "$URL" -o "$OUT"
echo "[vrm] saved -> $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
echo "License: CC0 (100Avatars R2 / Open Source Avatars)"
