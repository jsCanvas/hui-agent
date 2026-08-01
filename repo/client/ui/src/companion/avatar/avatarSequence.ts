import type { AvatarMode, SpeechSequenceKey } from "./types";

export type SequenceDef = {
  dir: string;
  pattern: string;
  count: number;
  fps: number;
  width?: number;
  height?: number;
};

export type AvatarManifest = {
  version: number;
  width: number;
  height: number;
  sequences: Record<string, SequenceDef>;
  modeMap: Record<AvatarMode, string>;
};

/** Companion 肖像最大宽度；高度按 manifest 宽高比计算，避免拉伸变形 */
export const AVATAR_MAX_WIDTH = 104;

export const AVATAR_DISPLAY = { w: AVATAR_MAX_WIDTH, h: 141 } as const;

export function computeDisplaySize(
  srcW: number,
  srcH: number,
  maxW: number = AVATAR_MAX_WIDTH,
): { w: number; h: number } {
  if (srcW <= 0 || srcH <= 0) return { w: maxW, h: AVATAR_DISPLAY.h };
  return { w: maxW, h: Math.max(1, Math.round((maxW * srcH) / srcW)) };
}

export function fitContainRect(
  boxW: number,
  boxH: number,
  srcW: number,
  srcH: number,
): { x: number; y: number; w: number; h: number } {
  const scale = Math.min(boxW / srcW, boxH / srcH);
  const w = srcW * scale;
  const h = srcH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}

export const AVATAR_MANIFEST_URL =
  import.meta.env.VITE_AVATAR_MANIFEST_URL ?? "/avatar/manifest.json";

export function frameUrl(seq: SequenceDef, frameNumber: number): string {
  const n = String(Math.max(1, frameNumber)).padStart(4, "0");
  const name = seq.pattern.replace("%04d", n);
  return `${seq.dir}/${name}`;
}

export function resolveSequenceKey(manifest: AvatarManifest, mode: AvatarMode): string {
  return manifest.modeMap[mode] ?? "idle";
}

export function resolveSpeechSequenceKey(
  manifest: AvatarManifest,
  mode: AvatarMode,
  speechSequence?: SpeechSequenceKey | null,
): string {
  if (
    mode === "speaking" &&
    speechSequence &&
    manifest.sequences[speechSequence]?.count
  ) {
    return speechSequence;
  }
  return resolveSequenceKey(manifest, mode);
}

export async function loadAvatarManifest(): Promise<AvatarManifest> {
  const resp = await fetch(AVATAR_MANIFEST_URL);
  if (!resp.ok) {
    throw new Error(`manifest ${resp.status}`);
  }
  return (await resp.json()) as AvatarManifest;
}

const MAX_FRAME_CACHE = 64;
const PREFETCH_AHEAD = 18;

export type DisplaySize = { w: number; h: number };

function loadImage(img: HTMLImageElement): Promise<void> {
  if (img.complete && img.naturalWidth > 0) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`frame load failed: ${img.src}`));
  });
}

async function decodeImageBitmap(
  img: HTMLImageElement,
  display: DisplaySize,
): Promise<ImageBitmap> {
  await img.decode?.().catch(() => undefined);
  return createImageBitmap(img, {
    resizeWidth: display.w,
    resizeHeight: display.h,
    resizeQuality: "medium",
  });
}

/** Lazy-load PNG frames; speaking 预解码为显示尺寸 ImageBitmap 以保证 60fps 流畅。 */
export class SequenceFrameCache {
  private readonly order: string[] = [];
  private readonly map = new Map<string, HTMLImageElement>();
  private readonly bitmapMap = new Map<string, ImageBitmap>();
  private readonly pinnedDirs = new Set<string>();
  private display: DisplaySize | null = null;

  private key(seq: SequenceDef, index: number): string {
    return `${seq.dir}#${index}`;
  }

  private bitmapKey(seq: SequenceDef, index: number, display: DisplaySize): string {
    return `${this.key(seq, index)}@${display.w}x${display.h}`;
  }

  setDisplaySize(display: DisplaySize): void {
    this.display = display;
  }

  pinSequence(seq: SequenceDef): void {
    this.pinnedDirs.add(seq.dir);
  }

  getFrame(seq: SequenceDef, index: number): HTMLImageElement {
    const i = Math.max(0, Math.min(seq.count - 1, index));
    const key = this.key(seq, i);
    let img = this.map.get(key);
    if (!img) {
      img = new Image();
      img.decoding = "async";
      img.src = frameUrl(seq, i + 1);
      this.map.set(key, img);
      this.touch(key, seq.dir);
    } else {
      this.touch(key, seq.dir);
    }
    return img;
  }

  getDisplayBitmap(
    seq: SequenceDef,
    index: number,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
  ): ImageBitmap | undefined {
    return this.bitmapMap.get(this.bitmapKey(seq, index, display));
  }

  /** Return a cached display-size bitmap for the same frame at any size, preferring closest size. */
  getAnyDisplayBitmap(seq: SequenceDef, index: number): ImageBitmap | undefined {
    const i = Math.max(0, Math.min(seq.count - 1, index));
    const prefix = `${seq.dir}#${i}@`;
    let best: ImageBitmap | undefined;
    let bestDiff = Infinity;
    const targetArea = (this.display?.w ?? AVATAR_DISPLAY.w) * (this.display?.h ?? AVATAR_DISPLAY.h);
    for (const [key, bitmap] of this.bitmapMap.entries()) {
      if (!key.startsWith(prefix)) continue;
      const sizePart = key.slice(prefix.length);
      const [wStr, hStr] = sizePart.split("x");
      const w = Number(wStr);
      const h = Number(hStr);
      if (!Number.isFinite(w) || !Number.isFinite(h)) continue;
      const area = w * h;
      const diff = Math.abs(area - targetArea);
      if (diff < bestDiff) {
        bestDiff = diff;
        best = bitmap;
      }
    }
    return best;
  }

  isReady(
    seq: SequenceDef,
    index: number,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
  ): boolean {
    if (this.pinnedDirs.has(seq.dir)) {
      return Boolean(this.getDisplayBitmap(seq, index, display));
    }
    const img = this.map.get(this.key(seq, index));
    return Boolean(img?.complete && img.naturalWidth > 0);
  }

  /** 解码单帧为显示尺寸 bitmap，不保留全分辨率 Image 引用。 */
  async loadDisplayBitmap(
    seq: SequenceDef,
    index: number,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
  ): Promise<ImageBitmap> {
    const i = Math.max(0, Math.min(seq.count - 1, index));
    const bk = this.bitmapKey(seq, i, display);
    const cached = this.bitmapMap.get(bk);
    if (cached) return cached;

    const img = new Image();
    img.decoding = "async";
    img.src = frameUrl(seq, i + 1);
    await loadImage(img);
    const bitmap = await decodeImageBitmap(img, display);
    this.bitmapMap.set(bk, bitmap);
    this.pinSequence(seq);
    return bitmap;
  }

  prefetchAhead(
    seq: SequenceDef,
    index: number,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
    ahead = PREFETCH_AHEAD,
  ): void {
    for (let off = 1; off <= ahead; off += 1) {
      const next = (index + off) % seq.count;
      if (this.isReady(seq, next, display)) continue;
      void this.loadDisplayBitmap(seq, next, display).catch(() => undefined);
    }
  }

  private touch(key: string, dir: string): void {
    const at = this.order.indexOf(key);
    if (at >= 0) this.order.splice(at, 1);
    this.order.push(key);

    if (this.pinnedDirs.has(dir)) return;

    while (this.order.length > MAX_FRAME_CACHE) {
      const evict = this.order.find((k) => !this.pinnedDirs.has(k.split("#")[0] ?? ""));
      if (!evict) break;
      const evictAt = this.order.indexOf(evict);
      if (evictAt >= 0) this.order.splice(evictAt, 1);
      this.map.delete(evict);
    }
  }

  async warmup(seq: SequenceDef, display: DisplaySize = this.display ?? AVATAR_DISPLAY): Promise<void> {
    await this.loadDisplayBitmap(seq, 0, display);
  }

  /** 预加载序列开头若干帧，保证 speaking 与音频同时起步。 */
  async preloadHead(
    seq: SequenceDef,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
    count = 24,
  ): Promise<void> {
    this.pinSequence(seq);
    const n = Math.min(count, seq.count);
    await Promise.all(
      Array.from({ length: n }, (_, i) => this.loadDisplayBitmap(seq, i, display)),
    );
  }

  /** 后台批量预加载整段序列为显示尺寸 bitmap（speaking 60fps 必需）。 */
  async preloadAll(
    seq: SequenceDef,
    display: DisplaySize = this.display ?? AVATAR_DISPLAY,
    concurrency = 6,
  ): Promise<void> {
    this.pinSequence(seq);
    let next = 0;
    const workers = Array.from({ length: concurrency }, async () => {
      while (next < seq.count) {
        const i = next;
        next += 1;
        await this.loadDisplayBitmap(seq, i, display);
      }
    });
    await Promise.all(workers);
  }
}

export type PlaybackState = {
  seqKey: string;
  acc: number;
  lastIndex: number;
  lastTime: number;
};

export function resetPlaybackState(state: PlaybackState, now = performance.now()): void {
  state.seqKey = "";
  state.acc = 0;
  state.lastIndex = 0;
  state.lastTime = now;
}

export function advancePlaybackIndex(
  seqKey: string,
  seq: SequenceDef,
  now: number,
  state: PlaybackState,
  cache: SequenceFrameCache,
  display: DisplaySize = AVATAR_DISPLAY,
  loop = true,
): number {
  if (seqKey === "idle" || seqKey === "listening") return 0;

  if (state.seqKey !== seqKey) {
    state.seqKey = seqKey;
    state.acc = 0;
    state.lastIndex = 0;
    state.lastTime = now;
  }

  const delta = state.lastTime > 0 ? Math.min(0.05, (now - state.lastTime) / 1000) : 0;
  state.lastTime = now;
  state.acc += delta * seq.fps;

  const raw = Math.floor(state.acc);
  const target = loop
    ? raw % seq.count
    : Math.max(0, Math.min(seq.count - 1, raw));
  cache.prefetchAhead(seq, target, display);

  if (cache.isReady(seq, target, display)) {
    state.lastIndex = target;
    return target;
  }

  for (let off = 1; off < Math.min(8, seq.count); off += 1) {
    const idx = (target + off) % seq.count;
    if (cache.isReady(seq, idx, display)) {
      state.lastIndex = idx;
      return idx;
    }
  }

  return state.lastIndex;
}

export function pickLoopFrameIndex(count: number, elapsedSec: number, fps: number): number {
  if (count <= 0) return 0;
  return Math.floor(elapsedSec * fps) % count;
}
