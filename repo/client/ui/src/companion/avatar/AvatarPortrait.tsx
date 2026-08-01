import { useEffect, useRef } from "react";
import type { AvatarMode } from "./types";
import { PORTRAIT_URL } from "./types";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  onFailed?: () => void;
};

/** Realistic portrait avatar with canvas lip-sync overlay. */
export function AvatarPortrait({ mouthOpen, mode, onFailed }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const img = new Image();
    img.src = PORTRAIT_URL;

    const draw = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx || !img.complete || img.naturalWidth === 0) return;

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight) * 1.06;
      const dw = img.naturalWidth * scale;
      const dh = img.naturalHeight * scale;
      const dx = (w - dw) / 2;
      const dy = (h - dh) / 2 - 6;
      ctx.drawImage(img, dx, dy, dw, dh);

      const cx = w * 0.5;
      const mouthY = h * 0.715;
      const speaking = mode === "speaking";
      const open = speaking ? Math.max(0.06, Math.min(1, mouthOpen)) : 0.02;

      if (speaking && open > 0.04) {
        ctx.fillStyle = "rgba(55, 18, 28, 0.72)";
        ctx.beginPath();
        ctx.ellipse(cx, mouthY, 6 + open * 5, 2 + open * 8, 0, 0, Math.PI * 2);
        ctx.fill();
      }

      if (mode === "listening") {
        ctx.strokeStyle = "rgba(52, 211, 153, 0.5)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(w / 2, h / 2 - 2, w * 0.4, 0, Math.PI * 2);
        ctx.stroke();
      }
    };

    img.onload = draw;
    img.onerror = () => onFailed?.();
    if (img.complete) draw();

    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [mouthOpen, mode, onFailed]);

  return (
    <div className={`avatar-portrait avatar-${mode}`} aria-hidden>
      <canvas
        ref={canvasRef}
        className={`avatar-canvas avatar-canvas-${mode}`}
        width={104}
        height={118}
      />
    </div>
  );
}
