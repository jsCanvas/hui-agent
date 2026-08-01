/** Real portrait sequence-frame player for the hero demo (from Companion video sources). */
(function () {
  const canvas = document.getElementById("demoAvatar");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  const cache = new Map();
  let manifest = null;
  let seqKey = "listening";
  let acc = 0;
  let lastIndex = -1;
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
    const head = Math.min(seq.count, 8);
    await Promise.all(
      Array.from({ length: head }, (_, i) => loadImage(frameUrl(seq, i))).map((p) =>
        p.catch(() => null),
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
    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(img, x, y, w, h);
  }

  async function drawFrame(key, index) {
    const seq = manifest?.sequences?.[key];
    if (!seq?.count) return;
    const idx = ((index % seq.count) + seq.count) % seq.count;
    if (idx === lastIndex && key === seqKey) return;
    try {
      const img = await loadImage(frameUrl(seq, idx));
      drawContain(img);
      lastIndex = idx;
    } catch {
      /* keep previous frame */
    }
  }

  function tick(now) {
    rafId = requestAnimationFrame(tick);
    if (!manifest) return;
    const seq = manifest.sequences[seqKey];
    if (!seq?.count) return;
    const dt = lastTime ? Math.min(64, now - lastTime) : 16;
    lastTime = now;
    acc += dt;
    const frameMs = 1000 / (seq.fps || 8);
    if (acc >= frameMs) {
      const steps = Math.floor(acc / frameMs);
      acc -= steps * frameMs;
      const next = lastIndex < 0 ? 0 : (lastIndex + steps) % seq.count;
      void drawFrame(seqKey, next);
    }
  }

  window.setDemoAvatarSequence = function (key) {
    if (!manifest?.sequences?.[key]) return;
    if (seqKey === key) return;
    seqKey = key;
    lastIndex = -1;
    acc = 0;
    void preloadSeq(key).then(() => drawFrame(key, 0));
  };

  window.setDemoAvatarStep = function (stepIndex) {
    const key = STEP_SEQUENCES[stepIndex] || "idle";
    window.setDemoAvatarSequence(key);
  };

  fetch("assets/avatar/manifest.json")
    .then((r) => r.json())
    .then(async (data) => {
      manifest = data;
      await preloadSeq("listening");
      await preloadSeq("speaking");
      await preloadSeq("idle");
      await drawFrame("listening", 0);
      lastTime = 0;
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => {
      ctx.fillStyle = "#2d3548";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    });
})();
