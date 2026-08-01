import { TTS_PROXY_URL, TTS_SPEECH_RATE } from "./types";

export type SpeakOptions = {
  voice?: string;
  rate?: string;
  pitch?: string;
  /** 音频实际开始播放时回调，用于与口型/序列帧同步 */
  onStart?: () => void;
  /** 音频播放结束时回调，用于停止 speaking 动画 */
  onStop?: () => void;
};

let activeStop: (() => void) | null = null;

export function stopCompanionSpeech() {
  activeStop?.();
  activeStop = null;
}

export async function speakWithLipSync(
  text: string,
  onLevel: (level: number) => void,
  options: SpeakOptions = {},
): Promise<void> {
  stopCompanionSpeech();

  const resp = await fetch(`${TTS_PROXY_URL}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      voice: options.voice ?? "zh-CN-XiaoxiaoNeural",
      rate: options.rate ?? TTS_SPEECH_RATE,
      pitch: options.pitch ?? "+2Hz",
    }),
  });
  if (!resp.ok) {
    throw new Error(`TTS HTTP ${resp.status}`);
  }

  const bytes = await resp.arrayBuffer();
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.45;
  const source = ctx.createBufferSource();
  source.buffer = await ctx.decodeAudioData(bytes.slice(0));
  source.connect(analyser);
  analyser.connect(ctx.destination);

  let raf = 0;
  let stopped = false;
  let stopNotified = false;

  const notifyStop = () => {
    if (stopNotified) return;
    stopNotified = true;
    options.onStop?.();
  };

  const cleanup = () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(raf);
    onLevel(0);
    try {
      source.stop();
    } catch {
      /* already stopped */
    }
    void ctx.close();
    activeStop = null;
  };

  activeStop = cleanup;

  await new Promise<void>((resolve, reject) => {
    const finish = () => {
      notifyStop();
      cleanup();
      resolve();
    };

    source.onended = () => {
      finish();
    };

    const tick = () => {
      if (stopped) return;
      const data = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(data);
      let sum = 0;
      const start = Math.floor(data.length * 0.05);
      const end = Math.floor(data.length * 0.45);
      for (let i = start; i < end; i++) sum += data[i];
      const avg = sum / Math.max(1, end - start);
      const level = Math.min(1, Math.pow(avg / 96, 0.85) * 1.15);
      onLevel(level);
      raf = requestAnimationFrame(tick);
    };

    try {
      options.onStart?.();
      source.start(0);
      tick();
    } catch (e) {
      cleanup();
      reject(e);
    }
  });
}

/** Procedural mouth motion when TTS plays on backend without audio analyser. */
export function proceduralMouthLevel(now = performance.now()): number {
  const base = (Math.sin(now / 95) + 1) / 2;
  const jitter = (Math.sin(now / 37) + 1) / 2;
  return Math.min(1, 0.15 + base * 0.55 + jitter * 0.2);
}
