/** HD portrait sequence player — same character as Companion seq-webp/speaking. */
(function () {
  const canvas = document.getElementById("demoAvatar");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  const cache = new Map();
  let manifest = null;
  let seqKey = "listening";
  let acc = 0;
  let frameIndex = 0;
  let lastTime = 0;
  let rafId = 0;

  const STEP_SEQUENCES = ["listening", "listening", "idle", "idle", "speaking"];

  function frameUrl(seq, index) {
    const n = String(index + 1).padStart(4, "0");
    return `${seq.dir}/${seq.pattern.replace("%04d", n)}`;
  }

  function loadImage(url) {
    if (cache.has(url)) return cache.get(url);
    const p = new Promise((resolve, reject) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(url));
      img.src = url;
    });
    cache.set(url, p);
    return p;
  }

  async function preloadSeq(key) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    await Promise.all(
      Array.from({ length: seq.count }, (_, i) =>
        loadImage(frameUrl(seq, i)).catch(() => null),
      ),
    );
  }

  function drawContain(img) {
    const cw = canvas.width;
    const ch = canvas.height;
    const iw = img.naturalWidth || img.width;
    const ih = img.naturalHeight || img.height;
    const scale = Math.min(cw / iw, ch / ih);
    const w = iw * scale;
    const h = ih * scale;
    const x = (cw - w) / 2;
    const y = (ch - h) / 2;
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, cw, ch);
    ctx.drawImage(img, x, y, w, h);
  }

  async function drawFrame(key, index) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    const idx = ((index % seq.count) + seq.count) % seq.count;
    try {
      const img = await loadImage(frameUrl(seq, idx));
      drawContain(img);
      frameIndex = idx;
    } catch {
      /* keep previous frame */
    }
  }

  function tick(now) {
    rafId = requestAnimationFrame(tick);
    if (!manifest) return;
    const seq = manifest.sequences[seqKey];
    if (!seq?.count) return;
    const dt = lastTime ? Math.min(50, now - lastTime) : 16;
    lastTime = now;
    acc += dt;
    const frameMs = 1000 / (seq.fps || 8);
    while (acc >= frameMs) {
      acc -= frameMs;
      const next = (frameIndex + 1) % seq.count;
      void drawFrame(seqKey, next);
    }
  }

  window.setDemoAvatarSequence = function (key) {
    if (!manifest?.sequences?.[key]) return;
    if (seqKey === key) return;
    seqKey = key;
    frameIndex = 0;
    acc = 0;
    void drawFrame(key, 0);
  };

  window.setDemoAvatarStep = function (stepIndex) {
    window.setDemoAvatarSequence(STEP_SEQUENCES[stepIndex] || "idle");
  };

  fetch("assets/avatar/manifest.json")
    .then((r) => r.json())
    .then(async (data) => {
      manifest = data;
      await Promise.all([
        preloadSeq("idle"),
        preloadSeq("listening"),
        preloadSeq("speaking"),
      ]);
      await drawFrame("listening", 0);
      lastTime = 0;
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => {
      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    });
})();
