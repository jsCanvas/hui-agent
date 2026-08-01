import { useEffect, useRef } from "react";

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type SpeechRecognitionOptions = {
  /** Session enabled (e.g. in call mode). Keeps recognition instance warm for PTT. */
  active: boolean;
  /** When false in PTT, calls stop() but keeps session; defaults to active. */
  listening?: boolean;
  lang?: string;
  /** Continuous session (free-talk). PTT uses false. */
  continuous?: boolean;
  /** Restart after onend when still listening (free-talk). */
  autoRestart?: boolean;
  onPartial?: (text: string) => void;
  onFinal: (text: string) => void;
  onError?: (message: string) => void;
  onListeningChange?: (listening: boolean) => void;
};

export function useSpeechRecognition({
  active,
  listening,
  lang = "zh-CN",
  continuous = true,
  autoRestart = true,
  onPartial,
  onFinal,
  onError,
  onListeningChange,
}: SpeechRecognitionOptions) {
  const recRef = useRef<SpeechRecognitionInstance | null>(null);
  const activeRef = useRef(active);
  const listenRef = useRef(listening ?? active);
  const partialRef = useRef("");
  const prevListenRef = useRef(false);
  const callbacks = useRef({ onPartial, onFinal, onError, onListeningChange });
  callbacks.current = { onPartial, onFinal, onError, onListeningChange };

  const shouldListen = listening ?? active;
  activeRef.current = active;
  listenRef.current = shouldListen;

  useEffect(() => {
    if (!active) {
      const rec = recRef.current;
      if (rec) {
        rec.onend = null;
        rec.onresult = null;
        rec.onerror = null;
        try {
          rec.abort();
        } catch {
          /* ignore */
        }
        recRef.current = null;
      }
      partialRef.current = "";
      callbacks.current.onListeningChange?.(false);
      return;
    }

    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      callbacks.current.onError?.("当前环境不支持 Web Speech，请改用文字输入");
      return;
    }

    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = continuous;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => callbacks.current.onListeningChange?.(true);
    rec.onend = () => {
      callbacks.current.onListeningChange?.(false);
      if (!activeRef.current || !listenRef.current) {
        return;
      }
      if (autoRestart) {
        try {
          rec.start();
        } catch {
          /* ignore restart race */
        }
      }
    };

    rec.onerror = (ev: SpeechRecognitionErrorEvent) => {
      if (ev.error === "aborted" || ev.error === "no-speech") return;
      const msg = ev.error === "not-allowed" ? "麦克风权限被拒绝" : ev.error;
      callbacks.current.onError?.(msg);
    };

    rec.onresult = (ev: SpeechRecognitionEvent) => {
      let interim = "";
      let finalText = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        const t = r[0]?.transcript?.trim() ?? "";
        if (!t) continue;
        if (r.isFinal) finalText += t;
        else interim += t;
      }
      if (interim) {
        partialRef.current = interim;
        callbacks.current.onPartial?.(interim);
      }
      if (finalText) {
        partialRef.current = "";
        callbacks.current.onFinal?.(finalText);
      }
    };

    recRef.current = rec;

    return () => {
      rec.onend = null;
      rec.onresult = null;
      rec.onerror = null;
      try {
        rec.abort();
      } catch {
        /* ignore */
      }
      if (recRef.current === rec) {
        recRef.current = null;
      }
      callbacks.current.onListeningChange?.(false);
    };
  }, [active, lang, continuous, autoRestart]);

  useEffect(() => {
    if (!active) {
      prevListenRef.current = false;
      return;
    }

    const rec = recRef.current;
    if (!rec) return;

    if (shouldListen) {
      partialRef.current = "";
      try {
        rec.start();
      } catch (e) {
        callbacks.current.onError?.(String(e));
      }
    } else if (prevListenRef.current) {
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
      window.setTimeout(() => {
        const pending = partialRef.current.trim();
        if (pending) {
          partialRef.current = "";
          callbacks.current.onFinal?.(pending);
        }
      }, 120);
    }

    prevListenRef.current = shouldListen;
  }, [active, shouldListen]);
}
