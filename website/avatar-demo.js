/** Portrait player — mirrors Companion AvatarSequencePlayer (seq-webp, static idle/listening). */
(function () {
  const canvas = document.getElementById("demoAvatar");
  if (!canvas) return;

  const DISPLAY_W = 104;
  const DISPLAY_H = 141;
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  const bitmapCache = new Map();
  let manifest = null;
  let seqKey = "listening";
  let playback = { seqKey: "", acc: 0, lastIndex: 0, lastTime: 0 };
  let rafId = 0;

  const STEP_SEQUENCES = ["listening", "listening", "idle", "idle", "speaking"];

  function frameUrl(seq, index) {
    const n = String(index + 1).padStart(4, "0");
    return `${seq.dir}/${seq.pattern.replace("%04d", n)}`;
  }

  function bitmapKey(seq, index) {
    return `${seq.dir}#${index}@${canvas.width}x${canvas.height}`;
  }

  async function loadDisplayBitmap(seq, index) {
    const i = Math.max(0, Math.min(seq.count - 1, index));
    const key = bitmapKey(seq, i);
    if (bitmapCache.has(key)) return bitmapCache.get(key);

    const img = new Image();
    img.decoding = "async";
    img.src = frameUrl(seq, i);
    await img.decode?.().catch(() => new Promise((res, rej) => {
      img.onload = () => res();
      img.onerror = () => rej(new Error(img.src));
    }));

    const bitmap = await createImageBitmap(img, {
      resizeWidth: canvas.width,
      resizeHeight: canvas.height,
      resizeQuality: "high",
    });
    bitmapCache.set(key, bitmap);
    return bitmap;
  }

  async function preloadSeq(key) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    if (key === "idle" || key === "listening") {
      await loadDisplayBitmap(seq, 0);
      return;
    }
    const head = Math.min(seq.count, 12);
    await Promise.all(
      Array.from({ length: head }, (_, i) =>
        loadDisplayBitmap(seq, i).catch(() => null),
      ),
    );
  }

  function drawBitmap(bitmap) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  }

  async function drawFrame(key, index) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    const idx = key === "idle" || key === "listening" ? 0 : index % seq.count;
    try {
      const bitmap = await loadDisplayBitmap(seq, idx);
      drawBitmap(bitmap);
      playback.lastIndex = idx;
    } catch {
      /* keep previous frame */
    }
  }

  function advanceIndex(key, seq, now) {
    if (key === "idle" || key === "listening") return 0;

    if (playback.seqKey !== key) {
      playback.seqKey = key;
      playback.acc = 0;
      playback.lastIndex = 0;
      playback.lastTime = now;
    }

    const delta =
      playback.lastTime > 0 ? Math.min(50, now - playback.lastTime) / 1000 : 0;
    playback.lastTime = now;
    playback.acc += delta * (seq.fps || 12);
    return Math.floor(playback.acc) % seq.count;
  }

  function tick(now) {
    rafId = requestAnimationFrame(tick);
    if (!manifest) return;
    const seq = manifest.sequences[seqKey];
    if (!seq?.count) return;

    const index = advanceIndex(seqKey, seq, now);
    if (index !== playback.lastIndex || playback.seqKey !== seqKey) {
      void drawFrame(seqKey, index);
    }

    if (seqKey === "speaking") {
      for (let off = 1; off <= 6; off += 1) {
        const next = (index + off) % seq.count;
        void loadDisplayBitmap(seq, next).catch(() => null);
      }
    }
  }

  function applyModeClass(key) {
    const stage = canvas.closest(".avatar-stage");
    if (!stage) return;
    stage.dataset.avatarMode = key;
  }

  window.setDemoAvatarSequence = function (key) {
    if (!manifest?.sequences?.[key]) return;
    if (seqKey === key) return;
    seqKey = key;
    playback = { seqKey: "", acc: 0, lastIndex: -1, lastTime: 0 };
    applyModeClass(key);
    void drawFrame(key, 0);
  };

  window.setDemoAvatarStep = function (stepIndex) {
    window.setDemoAvatarSequence(STEP_SEQUENCES[stepIndex] || "idle");
  };

  fetch("assets/avatar/manifest.json")
    .then((r) => r.json())
    .then(async (data) => {
      manifest = data;
      canvas.width = DISPLAY_W * 2;
      canvas.height = DISPLAY_H * 2;
      await Promise.all([
        preloadSeq("idle"),
        preloadSeq("listening"),
        preloadSeq("speaking"),
      ]);
      applyModeClass("listening");
      await drawFrame("listening", 0);
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    });
})();
