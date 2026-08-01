import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isTauriApp } from "./useCompanionBackendStt";

export function useCompanionDrawTools() {
  const [brushActive, setBrushActive] = useState(false);

  useEffect(() => {
    if (!isTauriApp()) return;
    let unlisten: (() => void) | undefined;
    void listen("companion-draw-exited", () => {
      setBrushActive(false);
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  const toggleBrush = useCallback(async () => {
    if (!isTauriApp()) return;
    const next = !brushActive;
    try {
      if (next) {
        await invoke("companion_draw_show");
      } else {
        await invoke("companion_draw_hide");
      }
      await invoke("companion_raise");
      setBrushActive(next);
    } catch (err) {
      console.warn("[draw] toggle brush failed:", err);
    }
  }, [brushActive]);

  const clearDrawings = useCallback(async () => {
    if (!isTauriApp()) return;
    try {
      await invoke("companion_draw_clear");
    } catch (err) {
      console.warn("[draw] clear failed:", err);
    }
  }, []);

  return {
    brushActive,
    toggleBrush,
    clearDrawings,
    supported: isTauriApp(),
  };
}
