import type { AvatarMode } from "./types";

const W = 104;
const H = 118;

type DrawState = {
  mode: AvatarMode;
  mouthOpen: number;
  timeSec: number;
  mouthSmooth: number;
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function blinkStrength(timeSec: number): number {
  const cycle = 4.2;
  const phase = timeSec % cycle;
  if (phase < 0.1) return Math.sin((phase / 0.1) * Math.PI);
  if (phase > cycle - 0.07) return Math.sin(((cycle - phase) / 0.07) * Math.PI) * 0.3;
  return 0;
}

function breathScale(timeSec: number, mode: AvatarMode): number {
  const speed = mode === "speaking" ? 5 : mode === "listening" ? 3 : 2.2;
  const amp = mode === "speaking" ? 0.014 : 0.01;
  return 1 + amp * Math.sin(timeSec * speed);
}

function mouthTarget(mode: AvatarMode, mouthOpen: number): number {
  if (mode === "speaking") return Math.max(0.1, Math.min(1, mouthOpen));
  if (mode === "completed") return 0.2;
  if (mode === "executing" || mode === "waiting") return 0.05;
  if (mode === "listening") return 0.07;
  return 0.03;
}

function modeGlow(mode: AvatarMode): string | null {
  switch (mode) {
    case "listening":
      return "rgba(52, 211, 153, 0.2)";
    case "speaking":
      return "rgba(251, 113, 133, 0.2)";
    case "executing":
    case "waiting":
      return "rgba(251, 191, 36, 0.14)";
    case "completed":
      return "rgba(244, 114, 182, 0.2)";
    default:
      return "rgba(251, 113, 133, 0.08)";
  }
}

function drawGlow(ctx: CanvasRenderingContext2D, cx: number, cy: number, color: string) {
  const g = ctx.createRadialGradient(cx, cy, 6, cx, cy, 54);
  g.addColorStop(0, color);
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(cx, cy, 54, 0, Math.PI * 2);
  ctx.fill();
}

function drawHairBack(ctx: CanvasRenderingContext2D, cx: number, cy: number, sway: number, t: number) {
  ctx.save();
  ctx.translate(sway * 0.5, 0);

  const wave1 = Math.sin(t * 1.3) * 3;
  const wave2 = Math.sin(t * 1.3 + 1.2) * 2.5;

  const base = ctx.createLinearGradient(cx - 50, cy - 50, cx + 50, cy + 58);
  base.addColorStop(0, "#241c20");
  base.addColorStop(0.35, "#4a3540");
  base.addColorStop(0.7, "#3d2f36");
  base.addColorStop(1, "#221a1e");

  // 大波浪外轮廓 — 蓬松长发
  ctx.fillStyle = base;
  ctx.beginPath();
  ctx.moveTo(cx - 44, cy - 6);
  ctx.bezierCurveTo(cx - 52, cy - 50, cx - 22, cy - 58, cx, cy - 54);
  ctx.bezierCurveTo(cx + 22, cy - 58, cx + 52, cy - 50, cx + 44, cy - 6);
  ctx.bezierCurveTo(cx + 48, cy + 18, cx + 38 + wave1, cy + 52, cx + 22, cy + 56);
  ctx.bezierCurveTo(cx + 8, cy + 58, cx - 8, cy + 58, cx - 22, cy + 56);
  ctx.bezierCurveTo(cx - 38 - wave2, cy + 52, cx - 48, cy + 18, cx - 44, cy - 6);
  ctx.closePath();
  ctx.fill();

  // 左侧大波浪卷
  ctx.fillStyle = "#352830";
  ctx.beginPath();
  ctx.moveTo(cx - 42, cy - 20);
  ctx.bezierCurveTo(cx - 50 + wave1, cy + 4, cx - 46, cy + 28, cx - 36 + wave1, cy + 50);
  ctx.bezierCurveTo(cx - 30, cy + 38, cx - 28, cy + 12, cx - 34, cy - 8);
  ctx.closePath();
  ctx.fill();

  // 右侧大波浪卷
  ctx.beginPath();
  ctx.moveTo(cx + 42, cy - 20);
  ctx.bezierCurveTo(cx + 50 - wave2, cy + 4, cx + 46, cy + 28, cx + 36 - wave2, cy + 50);
  ctx.bezierCurveTo(cx + 30, cy + 38, cx + 28, cy + 12, cx + 34, cy - 8);
  ctx.closePath();
  ctx.fill();

  // 波浪高光线条
  ctx.strokeStyle = "rgba(255, 228, 235, 0.14)";
  ctx.lineWidth = 1.6;
  ctx.lineCap = "round";
  const strands: [number, number, number, number, number, number][] = [
    [cx - 30 + wave1, cy - 24, cx - 38, cy + 2, cx - 32, cy + 28],
    [cx - 18, cy - 18, cx - 24 + wave2, cy + 8, cx - 20, cy + 36],
    [cx + 30 - wave2, cy - 24, cx + 38, cy + 2, cx + 32, cy + 28],
    [cx + 18, cy - 18, cx + 24 - wave1, cy + 8, cx + 20, cy + 36],
  ];
  for (const [x1, y1, x2, y2, x3, y3] of strands) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.quadraticCurveTo(x2, y2, x3, y3);
    ctx.stroke();
  }

  ctx.restore();
}

function drawHairSideWaves(ctx: CanvasRenderingContext2D, cx: number, cy: number, sway: number, t: number) {
  ctx.save();
  ctx.translate(sway * 0.35, 0);
  const w = Math.sin(t * 1.6) * 2;

  ctx.fillStyle = "#2f2328";
  ctx.beginPath();
  ctx.moveTo(cx - 32, cy + 4);
  ctx.bezierCurveTo(cx - 40 + w, cy + 18, cx - 36, cy + 36, cx - 26 + w, cy + 48);
  ctx.bezierCurveTo(cx - 22, cy + 32, cx - 24, cy + 16, cx - 28, cy + 6);
  ctx.closePath();
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(cx + 32, cy + 4);
  ctx.bezierCurveTo(cx + 40 - w, cy + 18, cx + 36, cy + 36, cx + 26 - w, cy + 48);
  ctx.bezierCurveTo(cx + 22, cy + 32, cx + 24, cy + 16, cx + 28, cy + 6);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

function drawHairFront(ctx: CanvasRenderingContext2D, cx: number, cy: number, sway: number) {
  ctx.save();
  ctx.translate(sway * 0.25, 0);

  // 轻薄空气刘海
  ctx.fillStyle = "#3d2f36";
  ctx.beginPath();
  ctx.moveTo(cx - 30, cy - 30);
  ctx.bezierCurveTo(cx - 16, cy - 44, cx + 16, cy - 44, cx + 30, cy - 30);
  ctx.bezierCurveTo(cx + 14, cy - 22, cx - 14, cy - 22, cx - 30, cy - 30);
  ctx.fill();

  // 刘海分缕
  ctx.strokeStyle = "rgba(255, 228, 235, 0.1)";
  ctx.lineWidth = 1;
  for (const off of [-12, 0, 12]) {
    ctx.beginPath();
    ctx.moveTo(cx + off, cy - 38);
    ctx.quadraticCurveTo(cx + off * 0.6, cy - 26, cx + off * 0.4, cy - 18);
    ctx.stroke();
  }

  ctx.restore();
}

function drawHairBow(ctx: CanvasRenderingContext2D, cx: number, cy: number, t: number) {
  const bx = cx + 28;
  const by = cy - 38 + Math.sin(t * 2.2) * 0.8;
  ctx.fillStyle = "#fb7185";
  ctx.beginPath();
  ctx.ellipse(bx - 5, by, 5.5, 4, -0.4, 0, Math.PI * 2);
  ctx.ellipse(bx + 5, by, 5.5, 4, 0.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#fff1f2";
  ctx.beginPath();
  ctx.arc(bx, by, 2.2, 0, Math.PI * 2);
  ctx.fill();
}

function drawFace(ctx: CanvasRenderingContext2D, cx: number, cy: number) {
  const skin = ctx.createRadialGradient(cx - 6, cy - 14, 2, cx, cy + 6, 36);
  skin.addColorStop(0, "#fffaf8");
  skin.addColorStop(0.45, "#ffe8e4");
  skin.addColorStop(1, "#ffd0c8");

  // 标准鹅蛋脸：上窄、颧骨宽、下尖
  ctx.beginPath();
  ctx.moveTo(cx, cy - 30);
  ctx.bezierCurveTo(cx + 20, cy - 28, cx + 25, cy - 10, cx + 24, cy + 8);
  ctx.bezierCurveTo(cx + 22, cy + 22, cx + 12, cy + 30, cx, cy + 32);
  ctx.bezierCurveTo(cx - 12, cy + 30, cx - 22, cy + 22, cx - 24, cy + 8);
  ctx.bezierCurveTo(cx - 25, cy - 10, cx - 20, cy - 28, cx, cy - 30);
  ctx.closePath();

  ctx.fillStyle = skin;
  ctx.fill();

  ctx.strokeStyle = "rgba(244, 63, 94, 0.08)";
  ctx.lineWidth = 0.9;
  ctx.stroke();

  // 下颌柔和阴影
  const jaw = ctx.createRadialGradient(cx, cy + 26, 2, cx, cy + 28, 14);
  jaw.addColorStop(0, "rgba(220, 160, 150, 0.12)");
  jaw.addColorStop(1, "rgba(220, 160, 150, 0)");
  ctx.fillStyle = jaw;
  ctx.beginPath();
  ctx.ellipse(cx, cy + 24, 10, 6, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawBlush(ctx: CanvasRenderingContext2D, cx: number, cy: number, mode: AvatarMode) {
  const strength = mode === "speaking" || mode === "completed" ? 0.34 : 0.26;
  const g = ctx.createRadialGradient(cx - 20, cy + 8, 1, cx - 20, cy + 8, 10);
  g.addColorStop(0, `rgba(251, 113, 133, ${strength})`);
  g.addColorStop(1, "rgba(251, 113, 133, 0)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.ellipse(cx - 20, cy + 8, 10, 6, -0.15, 0, Math.PI * 2);
  ctx.fill();

  const g2 = ctx.createRadialGradient(cx + 20, cy + 8, 1, cx + 20, cy + 8, 10);
  g2.addColorStop(0, `rgba(251, 113, 133, ${strength})`);
  g2.addColorStop(1, "rgba(251, 113, 133, 0)");
  ctx.fillStyle = g2;
  ctx.beginPath();
  ctx.ellipse(cx + 20, cy + 8, 10, 6, 0.15, 0, Math.PI * 2);
  ctx.fill();
}

function drawEye(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  blink: number,
  mode: AvatarMode,
  side: -1 | 1,
) {
  const attentive = mode === "listening";
  const thinking = mode === "executing" || mode === "waiting";
  const happy = mode === "completed";

  const rx = attentive ? 8.5 : 7.8;
  const ryBase = attentive ? 10 : happy ? 7 : 9.2;
  const ry = Math.max(0.6, ryBase * (1 - blink * 0.94));
  const lookX = thinking ? side * 1.8 : attentive ? side * 0.8 : 0;
  const lookY = thinking ? -2 : happy ? 1.5 : 0.5;

  ctx.save();
  ctx.translate(x, y);

  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.ellipse(0, 0, rx + 1, ry + 1.5, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "rgba(30, 20, 25, 0.85)";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.ellipse(0, -0.5, rx + 0.5, ry * 0.55, 0, Math.PI, 0);
  ctx.stroke();

  if (happy) {
    ctx.strokeStyle = "#9f1239";
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.arc(0, 2, 6.5, side === -1 ? 2.5 : 0.5, side === -1 ? Math.PI - 0.5 : Math.PI - 2.5);
    ctx.stroke();
    ctx.restore();
    return;
  }

  const iris = ctx.createRadialGradient(lookX - 1, lookY - 1, 0.5, lookX, lookY, rx * 0.72);
  iris.addColorStop(0, "#d97757");
  iris.addColorStop(0.45, "#9a4b42");
  iris.addColorStop(1, "#5c2f32");
  ctx.fillStyle = iris;
  ctx.beginPath();
  ctx.ellipse(lookX, lookY + 0.5, rx * 0.68, ry * 0.72, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#1a1214";
  ctx.beginPath();
  ctx.ellipse(lookX, lookY + 1, rx * 0.34, ry * 0.42, 0, 0, Math.PI * 2);
  ctx.fill();

  if (blink < 0.7) {
    ctx.fillStyle = "rgba(255,255,255,0.95)";
    ctx.beginPath();
    ctx.ellipse(lookX - side * 2.2, lookY - 2.5, 2.4, 1.8, -0.3, 0, Math.PI * 2);
    ctx.arc(lookX + side * 2.5, lookY + 1.5, 1.1, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = "rgba(30, 20, 25, 0.55)";
  ctx.lineWidth = 1.2;
  for (let i = 0; i < 3; i += 1) {
    const lx = -rx + 2 + i * (rx * 0.55);
    ctx.beginPath();
    ctx.moveTo(lx, ry * 0.55);
    ctx.lineTo(lx - side * 1.2, ry * 0.55 + 3.5);
    ctx.stroke();
  }

  ctx.restore();
}

function drawBrows(ctx: CanvasRenderingContext2D, cx: number, cy: number, mode: AvatarMode) {
  const thinking = mode === "executing" || mode === "waiting";
  ctx.strokeStyle = "rgba(74, 45, 52, 0.72)";
  ctx.lineWidth = 1.3;
  ctx.lineCap = "round";

  const lift = mode === "listening" ? -2 : thinking ? -3 : -0.5;

  ctx.beginPath();
  ctx.moveTo(cx - 26, cy - 20 + lift);
  ctx.quadraticCurveTo(cx - 15, cy - 27 + lift, cx - 5, cy - 22 + lift);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(cx + 5, cy - 22 + lift);
  ctx.quadraticCurveTo(cx + 15, cy - 27 + lift, cx + 26, cy - 20 + lift);
  ctx.stroke();
}

function drawNose(ctx: CanvasRenderingContext2D, cx: number, cy: number) {
  ctx.strokeStyle = "rgba(190, 120, 110, 0.35)";
  ctx.lineWidth = 1;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(cx, cy + 4);
  ctx.quadraticCurveTo(cx + 1.5, cy + 9, cx, cy + 11);
  ctx.stroke();
}

function drawLips(ctx: CanvasRenderingContext2D, cx: number, cy: number, open: number, mode: AvatarMode) {
  const y = cy + 19;

  if (open > 0.12) {
    const rx = 5 + open * 8;
    const ry = 2 + open * 10;
    ctx.fillStyle = "#881337";
    ctx.beginPath();
    ctx.ellipse(cx, y + open * 1.5, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fda4af";
    ctx.beginPath();
    ctx.ellipse(cx, y + open * 1.2 - ry * 0.2, rx * 0.85, ry * 0.35, 0, Math.PI, 0);
    ctx.fill();
    return;
  }

  const lip = ctx.createLinearGradient(cx - 10, y - 3, cx + 10, y + 4);
  lip.addColorStop(0, "#fb7185");
  lip.addColorStop(0.5, "#f43f5e");
  lip.addColorStop(1, "#e11d48");

  ctx.fillStyle = lip;
  ctx.beginPath();
  ctx.moveTo(cx - 9, y);
  ctx.bezierCurveTo(cx - 4, y - 3.5, cx + 4, y - 3.5, cx + 9, y);
  ctx.bezierCurveTo(cx + 4, y + 1.5, cx - 4, y + 1.5, cx - 9, y);
  ctx.fill();

  ctx.strokeStyle = "rgba(159, 18, 57, 0.35)";
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(cx - 8, y + 0.2);
  ctx.quadraticCurveTo(cx, y + 2.8, cx + 8, y + 0.2);
  ctx.stroke();

  if (mode === "completed" || mode === "conversation" || mode === "resting") {
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.beginPath();
    ctx.ellipse(cx - 3, y - 1.5, 3, 1.2, -0.2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawAccessory(ctx: CanvasRenderingContext2D, cx: number, cy: number, mode: AvatarMode, t: number) {
  if (mode === "executing" || mode === "waiting") {
    ctx.fillStyle = "rgba(251, 191, 36, 0.9)";
    ctx.font = "500 10px SF Pro Text, PingFang SC, sans-serif";
    ctx.textAlign = "center";
    const dots = ["·", "··", "···"];
    ctx.fillText(dots[Math.floor(t * 2.2) % dots.length], cx + 32, cy - 36);
  }

  if (mode === "listening") {
    ctx.fillStyle = "rgba(52, 211, 153, 0.8)";
    for (let i = 0; i < 3; i += 1) {
      const px = cx + 30 + i * 5;
      const py = cy - 30 + Math.sin(t * 5 + i) * 2;
      ctx.beginPath();
      ctx.arc(px, py, 1.2 + i * 0.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

export function drawCartoonAvatar(
  ctx: CanvasRenderingContext2D,
  state: DrawState,
): DrawState {
  const { mode, mouthOpen, timeSec } = state;
  ctx.clearRect(0, 0, W, H);

  const cx = W / 2;
  const cy = H / 2 + 4;
  const blink = blinkStrength(timeSec);
  const scale = breathScale(timeSec, mode);
  const sway = Math.sin(timeSec * 1.5) * 1.4;
  const mouthSmooth = lerp(state.mouthSmooth, mouthTarget(mode, mouthOpen), mode === "speaking" ? 0.32 : 0.16);

  const glow = modeGlow(mode);
  if (glow) drawGlow(ctx, cx, cy, glow);

  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(scale, scale);
  ctx.translate(-cx, -cy);

  drawHairBack(ctx, cx, cy, sway, timeSec);
  drawFace(ctx, cx, cy);
  drawBlush(ctx, cx, cy, mode);
  drawBrows(ctx, cx, cy, mode);

  const eyeY = cy - 6;
  const eyeGap = mode === "executing" || mode === "waiting" ? 11 : 15;
  drawEye(ctx, cx - eyeGap, eyeY, blink, mode, -1);
  drawEye(ctx, cx + eyeGap, eyeY, blink, mode, 1);

  drawNose(ctx, cx, cy);
  drawLips(ctx, cx, cy, mouthSmooth, mode);
  drawHairSideWaves(ctx, cx, cy, sway, timeSec);
  drawHairFront(ctx, cx, cy, sway);
  drawHairBow(ctx, cx, cy, timeSec);
  drawAccessory(ctx, cx, cy, mode, timeSec);

  ctx.restore();

  return { ...state, mouthSmooth };
}

export const CARTOON_AVATAR_SIZE = { w: W, h: H };
