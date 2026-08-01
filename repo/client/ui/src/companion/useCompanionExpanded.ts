import { useCallback, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { LogicalPosition, LogicalSize } from "@tauri-apps/api/dpi";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AVATAR_MAX_WIDTH } from "./avatar/avatarSequence";
import {
  COMPANION_WINDOW_SIZE,
  enterCompanionPortraitFullscreen,
  isTauriCompanionWindow,
} from "./useCompanionWindow";

type CompactSnapshot = {
  width: number;
  height: number;
  x: number;
  y: number;
};

function estimateExpandedMaxWidth(): number {
  if (typeof window === "undefined") return AVATAR_MAX_WIDTH * 6;
  // Use the screen work area so the preloaded expanded size matches the actual
  // expanded window even when the Companion is currently in compact mode.
  return Math.max(AVATAR_MAX_WIDTH * 2, Math.floor(window.screen.availWidth * 0.88 * 0.8));
}

export function useCompanionExpanded() {
  const [expanded, setExpanded] = useState(false);
  const [avatarMaxWidth, setAvatarMaxWidth] = useState(AVATAR_MAX_WIDTH);
  const [expandedAvatarMaxWidth, setExpandedAvatarMaxWidth] = useState(estimateExpandedMaxWidth);
  const compactRef = useRef<CompactSnapshot | null>(null);

  const toggleExpanded = useCallback(async () => {
    if (!isTauriCompanionWindow()) {
      setExpanded((prev) => {
        const next = !prev;
        const nextWidth = next ? Math.floor(window.innerWidth * 0.88 * 0.8) : AVATAR_MAX_WIDTH;
        setAvatarMaxWidth(nextWidth);
        if (next) setExpandedAvatarMaxWidth(nextWidth);
        return next;
      });
      return;
    }

    const appWindow = getCurrentWindow();
    if (!expanded) {
      const scale = await appWindow.scaleFactor();
      const [outer, pos] = await Promise.all([appWindow.outerSize(), appWindow.outerPosition()]);
      compactRef.current = {
        width: outer.width / scale,
        height: outer.height / scale,
        x: pos.x / scale,
        y: pos.y / scale,
      };

      const layout = await enterCompanionPortraitFullscreen();
      if (layout) {
        setAvatarMaxWidth(layout.avatarMaxWidth);
        setExpandedAvatarMaxWidth(layout.avatarMaxWidth);
        setExpanded(true);
      }
      return;
    }

    const snap = compactRef.current;
    if (snap) {
      await appWindow.setSize(new LogicalSize(snap.width, snap.height));
      await appWindow.setPosition(new LogicalPosition(snap.x, snap.y));
    } else {
      await appWindow.setSize(
        new LogicalSize(COMPANION_WINDOW_SIZE.width, COMPANION_WINDOW_SIZE.idleHeight),
      );
    }
    compactRef.current = null;
    setAvatarMaxWidth(AVATAR_MAX_WIDTH);
    setExpanded(false);
  }, [expanded]);

  const exitApp = useCallback(() => {
    if (isTauriCompanionWindow()) {
      void invoke("app_exit");
      return;
    }
    window.close();
  }, []);

  return { expanded, toggleExpanded, exitApp, avatarMaxWidth, expandedAvatarMaxWidth };
}
