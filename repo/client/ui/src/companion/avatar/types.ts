export type AvatarMode =
  | "resting"
  | "waiting"
  | "executing"
  | "completed"
  | "conversation"
  | "listening"
  | "speaking"
  | "monitoring";

export const AVATAR_STATE_LABEL: Record<AvatarMode, string> = {
  resting: "休息",
  waiting: "等待",
  executing: "执行中",
  completed: "执行完成",
  conversation: "对话",
  listening: "聆听",
  speaking: "播报",
  monitoring: "监听中",
};

/** Default sequence-frame portrait. Set VITE_USE_SEQUENCE=false to hide avatar. */
export const USE_SEQUENCE = import.meta.env.VITE_USE_SEQUENCE !== "false";

/** Optional 3D VRM. Set VITE_USE_VRM=true to enable. */
export const USE_VRM = import.meta.env.VITE_USE_VRM === "true";

export const VRM_MODEL_URL =
  import.meta.env.VITE_VRM_MODEL_URL ?? "/vrm/companion.vrm";

/** CC0 MoonGirl — 100Avatars R2 (Open Source Avatars / Arweave) */
export const VRM_MODEL_CDN =
  import.meta.env.VITE_VRM_MODEL_CDN ??
  "https://arweave.net/m39XL2LTq_7B1kSjjfsiA_DDqFlfs0TOWjFZy-x8Grc";

/** Set VITE_USE_LIVE2D=true to prefer Cubism Live2D over VRM. */
export const USE_LIVE2D = import.meta.env.VITE_USE_LIVE2D === "true";

export const LIVE2D_MODEL_URL =
  import.meta.env.VITE_LIVE2D_MODEL_URL ??
  "/live2d/mao/Mao.model3.json";

export const LIVE2D_MODEL_CDN =
  "https://cdn.jsdelivr.net/gh/Live2D/CubismWebSamples@master/Samples/Resources/Mao/Mao.model3.json";

export const CUBISM_CORE_URL =
  import.meta.env.VITE_CUBISM_CORE_URL ??
  "/live2d/live2dcubismcore.min.js";

export const CUBISM_CORE_CDN = "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js";

export const TTS_PROXY_URL =
  import.meta.env.VITE_TTS_PROXY_URL ?? "http://127.0.0.1:8896";

/** 播报语速倍数（1.0 = 正常）；Edge TTS 使用相对百分比 rate */
export const TTS_SPEECH_SPEED = 1.1;
export const TTS_SPEECH_RATE = "+10%";

export type AgentLifecycle = "resting" | "waiting" | "executing" | "completed" | "conversation";

/** 播报时使用的序列：默认 speaking，电话首次问候用 greetings */
export type SpeechSequenceKey = "speaking" | "greetings";
