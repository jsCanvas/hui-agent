import { useEffect, useRef } from "react";
import { CARTOON_AVATAR_SIZE, drawCartoonAvatar } from "./avatarCartoonDraw";
import type { AvatarMode } from "./types";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  maxDisplayWidth?: number;
};

/** Canvas-drawn companion mascot with mode-aware expressions. */
export function AvatarFallback({ mouthOpen, mode, maxDisplayWidth }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouthRef = useRef(mouthOpen);
  const modeRef = useRef(mode);
  const mouthSmoothRef = useRef(0.04);

  mouthRef.current = mouthOpen;
  modeRef.current = mode;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let raf = 0;
    const start = performance.now();

    const frame = (now: number) => {
      const next = drawCartoonAvatar(ctx, {
        mode: modeRef.current,
        mouthOpen: mouthRef.current,
        timeSec: (now - start) / 1000,
        mouthSmooth: mouthSmoothRef.current,
      });
      mouthSmoothRef.current = next.mouthSmooth;
      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      className={`avatar-portrait avatar-cartoon avatar-${mode}`}
      style={
        maxDisplayWidth && maxDisplayWidth > CARTOON_AVATAR_SIZE.w
          ? {
              width: maxDisplayWidth,
              height: Math.round((maxDisplayWidth * CARTOON_AVATAR_SIZE.h) / CARTOON_AVATAR_SIZE.w),
            }
          : undefined
      }
      aria-hidden
    >
      <canvas
        ref={canvasRef}
        className={`avatar-canvas avatar-canvas-${mode} avatar-${mode}`}
        width={CARTOON_AVATAR_SIZE.w}
        height={CARTOON_AVATAR_SIZE.h}
        style={
          maxDisplayWidth && maxDisplayWidth > CARTOON_AVATAR_SIZE.w
            ? {
                width: maxDisplayWidth,
                height: Math.round(
                  (maxDisplayWidth * CARTOON_AVATAR_SIZE.h) / CARTOON_AVATAR_SIZE.w,
                ),
              }
            : undefined
        }
      />
    </div>
  );
}
