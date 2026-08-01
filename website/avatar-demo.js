/** Single portrait — exact seq-webp/greetings/frame_0001.webp, scaled like Companion. */
(function () {
  const canvas = document.getElementById("demoAvatar");
  if (!canvas) return;

  const DISPLAY_W = 104;
  const DISPLAY_H = 141;
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  let portraitBitmap = null;
  let mode = "listening";

  function applyMode(next) {
    mode = next;
    const stage = canvas.closest(".avatar-stage");
    if (stage) stage.dataset.avatarMode = next;
  }

  function draw() {
    if (!portraitBitmap) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(portraitBitmap, 0, 0, canvas.width, canvas.height);
  }

  async function loadPortrait(url) {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    await img.decode?.().catch(
      () =>
        new Promise((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error(url));
        }),
    );
    canvas.width = DISPLAY_W * 2;
    canvas.height = DISPLAY_H * 2;
    portraitBitmap = await createImageBitmap(img, {
      resizeWidth: canvas.width,
      resizeHeight: canvas.height,
      resizeQuality: "high",
    });
    draw();
  }

  window.setDemoAvatarMode = applyMode;

  window.setDemoAvatarStep = function (stepIndex) {
    if (stepIndex >= 4) applyMode("speaking");
    else if (stepIndex <= 1) applyMode("listening");
    else applyMode("idle");
  };

  fetch("assets/avatar/manifest.json")
    .then((r) => r.json())
    .then((data) => loadPortrait(data.portrait || "assets/avatar/portrait.webp"))
    .then(() => applyMode("listening"))
    .catch(() => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    });
})();
