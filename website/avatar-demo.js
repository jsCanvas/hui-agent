/** Tab-driven seq-webp loop player (listening / greetings / idle / speaking). */
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
  let frameIndex = 0;
  let playback = { seqKey: "", acc: 0, lastTime: 0 };
  let rafId = 0;

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
    await img.decode?.().catch(
      () =>
        new Promise((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error(img.src));
        }),
    );

    const bitmap = await createImageBitmap(img, {
      resizeWidth: canvas.width,
      resizeHeight: canvas.height,
      resizeQuality: "high",
    });
    bitmapCache.set(key, bitmap);
    return bitmap;
  }

  async function preloadSeq(key, head) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    const n = Math.min(head, seq.count);
    await Promise.all(
      Array.from({ length: n }, (_, i) =>
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
    const idx = ((index % seq.count) + seq.count) % seq.count;
    try {
      const bitmap = await loadDisplayBitmap(seq, idx);
      drawBitmap(bitmap);
      frameIndex = idx;
    } catch {
      /* keep previous frame */
    }
  }

  function advanceIndex(key, seq, now) {
    if (playback.seqKey !== key) {
      playback.seqKey = key;
      playback.acc = 0;
      playback.lastTime = now;
    }
    const dt = playback.lastTime ? Math.min(50, now - playback.lastTime) / 1000 : 0;
    playback.lastTime = now;
    playback.acc += dt * (seq.fps || 8);
    return Math.floor(playback.acc) % seq.count;
  }

  function applyMode(key) {
    const stage = canvas.closest(".avatar-stage");
    if (stage) stage.dataset.avatarMode = key;
  }

  function tick(now) {
    rafId = requestAnimationFrame(tick);
    if (!manifest) return;
    const seq = manifest.sequences[seqKey];
    if (!seq?.count) return;

    const index = advanceIndex(seqKey, seq, now);
    if (index !== frameIndex) void drawFrame(seqKey, index);

    for (let off = 1; off <= 4; off += 1) {
      void loadDisplayBitmap(seq, (index + off) % seq.count).catch(() => null);
    }
  }

  window.setDemoAvatarStep = function (stepIndex) {
    const key = manifest?.stepMap?.[stepIndex] || "listening";
    if (key === seqKey) return;
    seqKey = key;
    frameIndex = -1;
    playback = { seqKey: "", acc: 0, lastTime: 0 };
    applyMode(key);
    void drawFrame(key, 0);
  };

  fetch("assets/avatar/manifest.json")
    .then((r) => r.json())
    .then(async (data) => {
      manifest = data;
      canvas.width = DISPLAY_W * 2;
      canvas.height = DISPLAY_H * 2;
      const keys = ["listening", "greetings", "idle", "speaking"];
      await Promise.all(keys.map((k) => preloadSeq(k, 8)));
      applyMode("listening");
      await drawFrame("listening", 0);
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => ctx.clearRect(0, 0, canvas.width, canvas.height));
})();
