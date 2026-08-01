import { useEffect, useRef, useState } from "react";
import type { AvatarMode, SpeechSequenceKey } from "./types";
import {
  advancePlaybackIndex,
  AVATAR_MAX_WIDTH,
  computeDisplaySize,
  fitContainRect,
  loadAvatarManifest,
  resetPlaybackState,
  resolveSpeechSequenceKey,
  SequenceFrameCache,
  type AvatarManifest,
  type PlaybackState,
} from "./avatarSequence";
import { registerSequencePrepare } from "./avatarSequenceRuntime";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  maxWidth?: number;
  expandedMaxWidth?: number;
  speechSequence?: SpeechSequenceKey | null;
  onFailed?: () => void;
};

/** Portrait avatar driven by pre-rendered video frame sequences. */
export function AvatarSequencePlayer({
  mode,
  maxWidth,
  expandedMaxWidth,
  speechSequence = null,
  onFailed,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const manifestRef = useRef<AvatarManifest | null>(null);
  const cacheRef = useRef(new SequenceFrameCache());
  const playbackRef = useRef<PlaybackState>({
    seqKey: "",
    acc: 0,
    lastIndex: 0,
    lastTime: 0,
  });
  const modeRef = useRef(mode);
  const displayRef = useRef({ w: AVATAR_MAX_WIDTH, h: 141 });
  const lastDrawnRef = useRef({ seqKey: "", index: -1 });
  const drawRectRef = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const [ready, setReady] = useState(false);
  const [display, setDisplay] = useState({ w: AVATAR_MAX_WIDTH, h: 141 });

  modeRef.current = mode;
  const speechSequenceRef = useRef(speechSequence);
  speechSequenceRef.current = speechSequence;

  useEffect(() => {
    resetPlaybackState(playbackRef.current);
    lastDrawnRef.current = { seqKey: "", index: -1 };

    if (mode === "speaking") return;

    const manifest = manifestRef.current;
    const canvas = canvasRef.current;
    if (!manifest || !canvas || !ready) return;

    const seqKey = resolveSpeechSequenceKey(manifest, mode, null);
    if (seqKey !== "idle" && seqKey !== "listening") return;

    const seq = manifest.sequences[seqKey];
    if (!seq?.count) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const { w, h } = displayRef.current;
    const bitmap = cacheRef.current.getDisplayBitmap(seq, 0, { w, h });
    if (bitmap) {
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(bitmap, 0, 0, w, h);
      lastDrawnRef.current = { seqKey, index: 0 };
    }
  }, [mode, speechSequence, ready]);

  useEffect(() => {
    if (!ready) {
      registerSequencePrepare(null);
      return;
    }

    registerSequencePrepare(async (key) => {
      const manifest = manifestRef.current;
      const seq = manifest?.sequences[key];
      if (!seq?.count) return;
      await cacheRef.current.preloadHead(seq, displayRef.current, 12);
    });

    return () => {
      registerSequencePrepare(null);
    };
  }, [ready, display.h, display.w]);
  const maxWidthRef = useRef(maxWidth ?? AVATAR_MAX_WIDTH);
  maxWidthRef.current = maxWidth ?? AVATAR_MAX_WIDTH;

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const manifest = await loadAvatarManifest();
        if (cancelled) return;
        manifestRef.current = manifest;
        const compactSize = computeDisplaySize(
          manifest.width,
          manifest.height,
          AVATAR_MAX_WIDTH,
        );
        const expandedSize = computeDisplaySize(
          manifest.width,
          manifest.height,
          Math.max(AVATAR_MAX_WIDTH * 2, expandedMaxWidth ?? maxWidthRef.current),
        );
        const currentSize = computeDisplaySize(
          manifest.width,
          manifest.height,
          maxWidthRef.current,
        );
        displayRef.current = currentSize;
        setDisplay(currentSize);

        const cache = cacheRef.current;
        cache.setDisplaySize(currentSize);

        // Preload both compact and expanded display sizes so toggling is instant.
        const sizes = [compactSize, expandedSize];
        await Promise.all(
          sizes.map(async (size) => {
            await cache.warmup(manifest.sequences.idle, size);
            const listening = manifest.sequences.listening;
            if (listening?.count) {
              await cache.warmup(listening, size);
            }
            const speaking = manifest.sequences.speaking;
            const greetings = manifest.sequences.greetings;
            if (speaking?.count) {
              await cache.preloadHead(speaking, size, 24);
            }
            if (greetings?.count) {
              await cache.preloadHead(greetings, size, 24);
            }
          }),
        );
        if (cancelled) return;
        setReady(true);

        // Avoid aggressive full expanded preloading on modest machines; preload
        // just enough head to start smoothly and let runtime prefetch handle the rest.
        const speaking = manifest.sequences.speaking;
        if (speaking?.count) {
          void cache
            .preloadHead(speaking, expandedSize, 36)
            .catch((e) => console.warn("[AvatarSequencePlayer] speaking expanded preload:", e));
        }
      } catch (e) {
        console.warn("[AvatarSequencePlayer] load failed:", e);
        onFailed?.();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [expandedMaxWidth, onFailed]);

  useEffect(() => {
    const manifest = manifestRef.current;
    if (!manifest || !ready) return;
    const size = computeDisplaySize(
      manifest.width,
      manifest.height,
      maxWidth ?? AVATAR_MAX_WIDTH,
    );
    if (size.w === display.w && size.h === display.h) return;
    displayRef.current = size;
    cacheRef.current.setDisplaySize(size);
    // Keep the previous canvas content until the new-size bitmap is ready.
    setDisplay(size);

    // Ensure the target size is decoded; it is usually preloaded at init.
    void (async () => {
      const idle = manifest.sequences.idle;
      await cacheRef.current.warmup(idle, size).catch(() => undefined);
      const speaking = manifest.sequences.speaking;
      if (speaking?.count && size.w > AVATAR_MAX_WIDTH) {
        void cacheRef.current.preloadAll(speaking, size, 6).catch(() => undefined);
      }
    })();
  }, [maxWidth, ready, display.h, display.w]);

  useEffect(() => {
    if (!ready) return;
    const canvas = canvasRef.current;
    const manifest = manifestRef.current;
    if (!canvas || !manifest) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    // Reset so the first frame after a resize (which resets the canvas buffer) is always drawn.
    lastDrawnRef.current = { seqKey: "", index: -1 };

    const { w, h } = display;
    // Keep canvas pixel buffer in sync with display size. Setting the attribute
    // rather than just the style ensures WebKit/Tauri allocates the backing store
    // at the intended resolution and avoids stale/zero-sized surfaces.
    canvas.width = w;
    canvas.height = h;
    const cache = cacheRef.current;
    let raf = 0;

    const draw = (now: number) => {
      const currentMode = modeRef.current;
      const activeSpeech = speechSequenceRef.current;
      const seqKey = resolveSpeechSequenceKey(manifest, currentMode, activeSpeech);
      const seqDef = manifest.sequences[seqKey];
      if (!seqDef?.count) {
        raf = requestAnimationFrame(draw);
        return;
      }

      const loop = seqKey !== "greetings";
      const index = advancePlaybackIndex(
        seqKey,
        seqDef,
        now,
        playbackRef.current,
        cache,
        { w, h },
        loop,
      );

      const last = lastDrawnRef.current;
      if (last.seqKey === seqKey && last.index === index) {
        raf = requestAnimationFrame(draw);
        return;
      }

      const bitmap = cache.getDisplayBitmap(seqDef, index, { w, h });
      if (bitmap) {
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(bitmap, 0, 0, w, h);
        lastDrawnRef.current = { seqKey, index };
      } else {
        // Fallback: scale from any cached display-size bitmap for this frame.
        const fallback = cache.getAnyDisplayBitmap(seqDef, index);
        if (fallback) {
          ctx.clearRect(0, 0, w, h);
          ctx.drawImage(fallback, 0, 0, w, h);
          lastDrawnRef.current = { seqKey, index };
        } else {
          const img = cache.getFrame(seqDef, index);
          if (img.complete && img.naturalWidth > 0) {
            const srcW = seqDef.width ?? img.naturalWidth;
            const srcH = seqDef.height ?? img.naturalHeight;
            drawRectRef.current = fitContainRect(w, h, srcW, srcH);
            const rect = drawRectRef.current;
            ctx.clearRect(0, 0, w, h);
            ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h);
            lastDrawnRef.current = { seqKey, index };
          } else {
            // Kick off decoding of the current frame so it appears as soon as possible.
            void cache.loadDisplayBitmap(seqDef, index, { w, h }).catch(() => undefined);
          }
        }
      }

      raf = requestAnimationFrame(draw);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        // The canvas buffer may have been cleared while hidden; force a redraw.
        lastDrawnRef.current = { seqKey: "", index: -1 };
      }
    };

    const onResize = () => {
      // The canvas CSS size or pixel size may have changed; force a redraw.
      lastDrawnRef.current = { seqKey: "", index: -1 };
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("resize", onResize);

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("resize", onResize);
    };
  }, [ready, display.h, display.w]);

  // Ensure the canvas itself is sized exactly to the pixel buffer, while CSS handles display scaling.
  // This avoids the browser creating mismatch between pixel size and layout size which can cause
  // the WebView surface to glitch or disappear on macOS after extended display time.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.style.width = `${display.w}px`;
    canvas.style.height = `${display.h}px`;
  }, [display.w, display.h]);

  return (
    <div
      className={`avatar-portrait avatar-sequence avatar-${mode}`}
      style={{ width: display.w, height: display.h }}
      aria-hidden
    >
      <canvas
        ref={canvasRef}
        className={`avatar-canvas avatar-canvas-${mode}`}
        width={display.w}
        height={display.h}
        style={{ width: display.w, height: display.h }}
      />
    </div>
  );
}
