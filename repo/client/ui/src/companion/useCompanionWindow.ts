import { useCallback, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { LogicalPosition, LogicalSize, PhysicalPosition } from "@tauri-apps/api/dpi";
import { getCurrentWindow, currentMonitor } from "@tauri-apps/api/window";
import {
  AVATAR_DISPLAY,
  AVATAR_MAX_WIDTH,
  computeDisplaySize,
} from "./avatar/avatarSequence";

const POS_KEY = "hui-agent.companion-position";
const PORTRAIT_ASPECT = AVATAR_MAX_WIDTH / AVATAR_DISPLAY.h;

export const COMPANION_WINDOW_SIZE = {
  width: 252,
  idleHeight: 243,
  callHeight: 275,
  callErrorHeight: 315,
} as const;

export function isTauriCompanionWindow(): boolean {
  return Boolean(
    (window as Window & { __TAURI_INTERNALS__?: unknown; __TAURI__?: unknown })
      .__TAURI_INTERNALS__ ??
      (window as Window & { __TAURI__?: unknown }).__TAURI__,
  );
}

function isTauriWindow(): boolean {
  return isTauriCompanionWindow();
}

export async function enterCompanionPortraitFullscreen(): Promise<{ avatarMaxWidth: number } | null> {
  if (!isTauriWindow()) return null;
  try {
    const win = getCurrentWindow();
    const monitor = await currentMonitor();
    if (!monitor) return null;

    const scale = monitor.scaleFactor;
    const area = monitor.workArea;
    const areaW = area.size.width / scale;
    const areaH = area.size.height / scale;
    const areaX = area.position.x / scale;
    const areaY = area.position.y / scale;

    // Shrink the expanded portrait by 20% overall.
    const expandedScale = 0.8;
    let height = areaH * expandedScale;
    let width = height * PORTRAIT_ASPECT;
    if (width > areaW * expandedScale) {
      width = areaW * expandedScale;
      height = width / PORTRAIT_ASPECT;
    }

    const x = areaX + (areaW - width) / 2;
    const y = areaY + (areaH - height) / 2;
    await win.setSize(new LogicalSize(width, height));
    await win.setPosition(new LogicalPosition(x, y));

    const pad = 16;
    const statusRow = 32;
    const avatarBoxH = Math.max(1, height - statusRow - pad * 2);
    const avatarBoxW = Math.max(1, width - pad * 2);
    const size = computeDisplaySize(
      AVATAR_MAX_WIDTH,
      AVATAR_DISPLAY.h,
      Math.floor(Math.min(avatarBoxW, avatarBoxH * PORTRAIT_ASPECT)),
    );
    return { avatarMaxWidth: size.w };
  } catch {
    return null;
  }
}

export async function syncCompanionWindowSize(calling: boolean, hasError = false) {
  if (!isTauriWindow()) return;
  try {
    const win = getCurrentWindow();
    let height: number = COMPANION_WINDOW_SIZE.idleHeight;
    if (calling) {
      height = hasError
        ? COMPANION_WINDOW_SIZE.callErrorHeight
        : COMPANION_WINDOW_SIZE.callHeight;
    }
    await win.setSize(new LogicalSize(COMPANION_WINDOW_SIZE.width, height));
  } catch {
    /* ignore */
  }
}

type DragState = {
  pointerId: number;
  /** 指针在屏幕上的位置减去窗口逻辑坐标，保持抓取点固定 */
  offsetX: number;
  offsetY: number;
  ready: boolean;
};

export function useCompanionWindow() {
  const dragState = useRef<DragState | null>(null);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);

    dragState.current = {
      pointerId: e.pointerId,
      offsetX: 0,
      offsetY: 0,
      ready: false,
    };

    void (async () => {
      try {
        const win = getCurrentWindow();
        const [scale, outer] = await Promise.all([win.scaleFactor(), win.outerPosition()]);
        const d = dragState.current;
        if (!d || d.pointerId !== e.pointerId) return;

        const winX = outer.x / scale;
        const winY = outer.y / scale;
        d.offsetX = e.screenX - winX;
        d.offsetY = e.screenY - winY;
        d.ready = true;
      } catch {
        dragState.current = null;
      }
    })();
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragState.current;
    if (!d || e.pointerId !== d.pointerId || !d.ready) return;
    e.preventDefault();

    const x = e.screenX - d.offsetX;
    const y = e.screenY - d.offsetY;
    void getCurrentWindow().setPosition(new LogicalPosition(x, y));
  }, []);

  const endDrag = useCallback((e: React.PointerEvent) => {
    const d = dragState.current;
    if (!d || e.pointerId !== d.pointerId) return;
    dragState.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    const win = getCurrentWindow();

    void (async () => {
      try {
        const raw = localStorage.getItem(POS_KEY);
        if (raw) {
          const { x, y } = JSON.parse(raw) as { x: number; y: number };
          await win.setPosition(new PhysicalPosition(x, y));
        } else {
          await invoke("companion_reset_position");
        }
      } catch {
        /* ignore */
      }

      unlisten = await win.onMoved(({ payload }) => {
        localStorage.setItem(POS_KEY, JSON.stringify({ x: payload.x, y: payload.y }));
      });
    })();

    return () => {
      unlisten?.();
    };
  }, []);

  const dragHandleProps = {
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
  };

  return { dragHandleProps };
}
