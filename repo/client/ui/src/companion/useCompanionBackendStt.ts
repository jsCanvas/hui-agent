import { useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";

type SttResponse = {
  ok?: boolean;
  text?: string;
  texts?: string[];
  error?: string;
  message?: string;
};

export function isTauriApp(): boolean {
  return Boolean(
    (window as Window & { __TAURI_INTERNALS__?: unknown; __TAURI__?: unknown })
      .__TAURI_INTERNALS__ ??
      (window as Window & { __TAURI__?: unknown }).__TAURI__,
  );
}

export type CompanionBackendSttOptions = {
  sessionActive: boolean;
  listening: boolean;
  continuous: boolean;
  onFinal: (text: string) => void;
  onError?: (message: string) => void;
  onListeningChange?: (listening: boolean) => void;
};

export function useCompanionBackendStt({
  sessionActive,
  listening,
  continuous,
  onFinal,
  onError,
  onListeningChange,
}: CompanionBackendSttOptions) {
  const prevListenRef = useRef(false);
  const callbacks = useRef({ onFinal, onError, onListeningChange });
  callbacks.current = { onFinal, onError, onListeningChange };

  useEffect(() => {
    if (!sessionActive) {
      void invoke<SttResponse>("companion_stt_stop").catch(() => {});
      callbacks.current.onListeningChange?.(false);
      return;
    }

    if (!continuous) {
      return;
    }

    let cancelled = false;
    void invoke<SttResponse>("companion_stt_start", { continuous: true }).then((res) => {
      if (cancelled) return;
      if (!res.ok) {
        callbacks.current.onError?.(res.message || res.error || "语音识别启动失败");
        return;
      }
      callbacks.current.onListeningChange?.(true);
    });

    const pollId = window.setInterval(() => {
      void invoke<SttResponse>("companion_stt_poll")
        .then((res) => {
          if (!res.ok) {
            if (res.error && res.error !== "NO_SPEECH") {
              callbacks.current.onError?.(res.message || res.error);
            }
            return;
          }
          for (const text of res.texts ?? []) {
            const trimmed = text.trim();
            if (trimmed) {
              callbacks.current.onFinal(trimmed);
            }
          }
        })
        .catch(() => {});
    }, 900);

    return () => {
      cancelled = true;
      window.clearInterval(pollId);
      void invoke<SttResponse>("companion_stt_stop").catch(() => {});
      callbacks.current.onListeningChange?.(false);
    };
  }, [sessionActive, continuous]);

  useEffect(() => {
    if (!sessionActive || continuous) {
      prevListenRef.current = listening;
      return;
    }

    if (listening && !prevListenRef.current) {
      void invoke<SttResponse>("companion_stt_start", { continuous: false }).then((res) => {
        if (!res.ok) {
          callbacks.current.onError?.(res.message || res.error || "麦克风启动失败");
          callbacks.current.onListeningChange?.(false);
          return;
        }
        callbacks.current.onListeningChange?.(true);
      });
    } else if (!listening && prevListenRef.current) {
      void invoke<SttResponse>("companion_stt_stop").then((res) => {
        callbacks.current.onListeningChange?.(false);
        if (res.ok && res.text?.trim()) {
          callbacks.current.onFinal(res.text.trim());
        } else if (!res.ok && res.error !== "NO_SPEECH") {
          callbacks.current.onError?.(res.message || res.error || "语音识别失败");
        }
      });
    }

    prevListenRef.current = listening;
  }, [sessionActive, listening, continuous]);
}
