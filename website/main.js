(function () {
  const steps = document.querySelectorAll(".flow-step");
  const statusEl = document.getElementById("demoStatus");
  const utteranceEl = document.getElementById("demoUtterance");
  const labels = ["监听中", "执行中", "Relay 转发", "读屏滚页", "播报完成"];
  const utterances = [
    "「用中文阅读这篇小说」",
    "「好的，我先读屏看一下」",
    "→ Cursor MCP",
    "get_screenshot · mouse_scroll",
    "companion_speak · 监听中",
  ];
  let i = 0;

  function tick() {
    steps.forEach((el, idx) => el.classList.toggle("active", idx === i));
    if (statusEl) statusEl.textContent = labels[i];
    if (utteranceEl) utteranceEl.textContent = utterances[i];
    i = (i + 1) % steps.length;
  }

  if (steps.length) {
    tick();
    setInterval(tick, 2200);
  }
})();
