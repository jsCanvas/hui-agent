import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";
import { ensureCubismCore } from "./loadCubismCore";
import type { AvatarMode } from "./types";
import { LIVE2D_MODEL_CDN, LIVE2D_MODEL_URL } from "./types";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  onFailed?: () => void;
};

type Live2DModelInstance = {
  scale: { set: (v: number) => void };
  anchor: { set: (x: number, y: number) => void };
  x: number;
  y: number;
  width: number;
  height: number;
  motion: (group: string, index?: number) => Promise<void>;
  internalModel: {
    motionManager: { update: (...args: unknown[]) => void };
    coreModel: {
      setParameterValueById: (id: string, value: number, weight?: number) => void;
      getParameterIndex: (id: string) => number;
    };
  };
  destroy: (opts?: { children?: boolean; texture?: boolean; baseTexture?: boolean }) => void;
};

const MOTION_BY_MODE: Partial<Record<AvatarMode, string>> = {
  executing: "TapBody",
  completed: "TapBody",
  speaking: "TapBody",
  conversation: "Idle",
};

async function resolveModelUrl(): Promise<string> {
  try {
    const resp = await fetch(LIVE2D_MODEL_URL, { method: "HEAD" });
    if (resp.ok) return LIVE2D_MODEL_URL;
  } catch {
    /* use CDN */
  }
  return LIVE2D_MODEL_CDN;
}

function safeSetParam(
  core: Live2DModelInstance["internalModel"]["coreModel"],
  id: string,
  value: number,
) {
  if (core.getParameterIndex(id) >= 0) {
    core.setParameterValueById(id, value, 1);
  }
}

function applyModeParams(model: Live2DModelInstance, mode: AvatarMode, mouthOpen: number) {
  const core = model.internalModel.coreModel;

  safeSetParam(core, "ParamAngleX", 0);
  safeSetParam(core, "ParamAngleY", 0);
  safeSetParam(core, "ParamAngleZ", 0);
  safeSetParam(core, "ParamEyeBallX", 0);
  safeSetParam(core, "ParamEyeBallY", 0);
  safeSetParam(core, "ParamBrowLY", 0);
  safeSetParam(core, "ParamBrowRY", 0);
  safeSetParam(core, "ParamMouthForm", 0);
  safeSetParam(core, "ParamMouthOpenY", mode === "speaking" ? Math.max(0, Math.min(1, mouthOpen)) : 0);

  switch (mode) {
    case "listening":
      safeSetParam(core, "ParamAngleX", -18);
      safeSetParam(core, "ParamEyeBallX", 0.35);
      safeSetParam(core, "ParamEyeLOpen", 1);
      safeSetParam(core, "ParamEyeROpen", 1);
      break;
    case "waiting":
    case "executing":
      safeSetParam(core, "ParamAngleY", -22);
      safeSetParam(core, "ParamEyeBallY", -0.35);
      safeSetParam(core, "ParamBrowLY", -0.45);
      safeSetParam(core, "ParamBrowRY", -0.45);
      break;
    case "completed":
      safeSetParam(core, "ParamAngleY", 12);
      safeSetParam(core, "ParamMouthForm", 1);
      safeSetParam(core, "ParamEyeLOpen", 0.85);
      safeSetParam(core, "ParamEyeROpen", 0.85);
      break;
    case "conversation":
      safeSetParam(core, "ParamAngleX", 14);
      safeSetParam(core, "ParamEyeBallX", 0.12);
      safeSetParam(core, "ParamMouthForm", 0.35);
      break;
    case "speaking":
      safeSetParam(core, "ParamAngleX", 6);
      safeSetParam(core, "ParamMouthForm", 0.5);
      break;
    case "resting":
    default:
      safeSetParam(core, "ParamAngleY", 4);
      break;
  }
}

function syncCanvasModeClass(canvas: HTMLCanvasElement | null, mode: AvatarMode) {
  if (!canvas) return;
  canvas.className = `avatar-canvas avatar-canvas-${mode}`;
}

export function AvatarLive2D({ mouthOpen, mode, onFailed }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const modelRef = useRef<Live2DModelInstance | null>(null);
  const mouthRef = useRef(mouthOpen);
  const modeRef = useRef(mode);
  const lastMotionRef = useRef<string | null>(null);
  const [failed, setFailed] = useState(false);

  mouthRef.current = mouthOpen;
  modeRef.current = mode;

  useEffect(() => {
    const host = hostRef.current;
    if (!host || failed) return;

    let disposed = false;
    let app: PIXI.Application | null = null;

    const boot = async () => {
      try {
        await ensureCubismCore();
        (window as Window & { PIXI?: typeof PIXI }).PIXI = PIXI;
        const { Live2DModel } = await import("pixi-live2d-display/cubism4");
        const modelUrl = await resolveModelUrl();
        const model = (await Live2DModel.from(modelUrl, {
          autoInteract: false,
        })) as unknown as Live2DModelInstance;

        if (disposed) {
          model.destroy({ children: true });
          return;
        }

        app = new PIXI.Application({
          width: 104,
          height: 118,
          backgroundAlpha: 0,
          antialias: true,
          resolution: window.devicePixelRatio || 1,
          autoDensity: true,
        });
        const canvas = app.view as HTMLCanvasElement;
        canvasRef.current = canvas;
        syncCanvasModeClass(canvas, modeRef.current);
        host.appendChild(canvas);

        const pad = 10;
        const scale =
          Math.min((104 - pad * 2) / model.width, (118 - pad * 2) / model.height) * 0.98;
        model.scale.set(scale);
        model.anchor.set(0.5, 0.5);
        model.x = 52;
        model.y = 60;
        app.stage.addChild(model as unknown as PIXI.DisplayObject);

        const updateFn = model.internalModel.motionManager.update.bind(model.internalModel.motionManager);
        model.internalModel.motionManager.update = (...args: unknown[]) => {
          updateFn(...args);
          applyModeParams(model, modeRef.current, mouthRef.current);
        };

        modelRef.current = model;
        applyModeParams(model, modeRef.current, mouthRef.current);
        void model.motion("Idle");
      } catch (e) {
        console.warn("[AvatarLive2D] fallback:", e);
        setFailed(true);
        onFailed?.();
      }
    };

    void boot();

    return () => {
      disposed = true;
      modelRef.current?.destroy({ children: true });
      modelRef.current = null;
      canvasRef.current = null;
      app?.destroy(true, { children: true, texture: true, baseTexture: true });
      app = null;
      host.replaceChildren();
    };
  }, [failed, onFailed]);

  useEffect(() => {
    const model = modelRef.current;
    syncCanvasModeClass(canvasRef.current, mode);
    if (!model) return;
    applyModeParams(model, mode, mouthOpen);

    const motionGroup = MOTION_BY_MODE[mode];
    if (motionGroup && lastMotionRef.current !== `${mode}:${motionGroup}`) {
      lastMotionRef.current = `${mode}:${motionGroup}`;
      void model.motion(motionGroup).catch(() => {
        void model.motion("Idle");
      });
    }
    if (!motionGroup && mode === "resting") {
      lastMotionRef.current = null;
    }
  }, [mouthOpen, mode]);

  if (failed) return null;

  return <div ref={hostRef} className={`avatar-live2d avatar-${mode}`} aria-hidden />;
}
