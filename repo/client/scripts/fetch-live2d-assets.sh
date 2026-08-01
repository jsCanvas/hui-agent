#!/usr/bin/env bash
# Download Live2D Cubism Core + official Mao sample model into ui/public/live2d/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_NAME="${1:-mao}"
MODEL_NAME="$(echo "$MODEL_NAME" | tr '[:upper:]' '[:lower:]')"
case "$MODEL_NAME" in
  mao|haru|hiyori) ;;
  *) echo "Unknown model: $MODEL_NAME (mao|haru|hiyori)"; exit 1 ;;
esac
MODEL_ID="$(echo "$MODEL_NAME" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')"
DEST="$ROOT/ui/public/live2d/$MODEL_NAME"
mkdir -p "$ROOT/ui/public/live2d"

echo "[live2d] Cubism Core..."
curl -fsSL "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js" \
  -o "$ROOT/ui/public/live2d/live2dcubismcore.min.js"

echo "[live2d] ${MODEL_ID} model3.json..."
mkdir -p "$DEST"
curl -fsSL "https://cdn.jsdelivr.net/gh/Live2D/CubismWebSamples@master/Samples/Resources/${MODEL_ID}/${MODEL_ID}.model3.json" \
  -o "$DEST/${MODEL_ID}.model3.json"

python3 - <<PY
import json, urllib.request, os
base = "$DEST"
model_id = "$MODEL_ID"
root = f"https://cdn.jsdelivr.net/gh/Live2D/CubismWebSamples@master/Samples/Resources/{model_id}/"
with open(os.path.join(base, f"{model_id}.model3.json")) as f:
    data = json.load(f)
files = set()
refs = data.get("FileReferences", {})
for key, val in refs.items():
    if key == "Motions":
        for motions in val.values():
            for motion in motions:
                files.add(motion.get("File"))
        continue
    if isinstance(val, str):
        files.add(val)
    elif isinstance(val, list):
        files.update(val)
for rel in sorted(files):
    if not rel:
        continue
    dest = os.path.join(base, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("  ", rel)
    urllib.request.urlretrieve(root + rel, dest)
print(f"[live2d] done ({len(files)} assets) -> ui/public/live2d/{model_id}/")
PY
