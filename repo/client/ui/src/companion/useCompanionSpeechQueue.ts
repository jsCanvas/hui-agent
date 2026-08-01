import { useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { stopCompanionSpeech } from "./avatar/companionTts";

type EnqueueOpts = {
  speakId?: string;
  utteranceId?: string;
  interrupt?: boolean;
};

const DEDUPE_MS = 12_000;
const MAX_SEEN_IDS = 256;

/** 串行播报队列：上一段播完再播下一段；去重 speak_id / 同 utterance 重复文本。 */
export function useCompanionSpeechQueue(
  speakReply: (text: string) => Promise<void>,
) {
  const chainRef = useRef<Promise<void>>(Promise.resolve());
  const seenSpeakIdsRef = useRef(new Set<string>());
  const recentTextRef = useRef(new Map<string, number>());

  const markSpeakDone = useCallback(async (speakId: string) => {
    if (!speakId) return;
    await invoke("companion_voice_speak_done", { speakId }).catch(() => {});
  }, []);

  const shouldSkipDuplicate = useCallback(
    (trimmed: string, speakId: string, utteranceId: string) => {
      if (speakId) {
        if (seenSpeakIdsRef.current.has(speakId)) {
          return true;
        }
        seenSpeakIdsRef.current.add(speakId);
        if (seenSpeakIdsRef.current.size > MAX_SEEN_IDS) {
          seenSpeakIdsRef.current.clear();
        }
      }
      const dedupeKey = `${utteranceId}:${trimmed}`;
      const lastAt = recentTextRef.current.get(dedupeKey);
      if (lastAt != null && Date.now() - lastAt < DEDUPE_MS) {
        return true;
      }
      recentTextRef.current.set(dedupeKey, Date.now());
      if (recentTextRef.current.size > MAX_SEEN_IDS) {
        recentTextRef.current.clear();
      }
      return false;
    },
    [],
  );

  const enqueueSpeak = useCallback(
    (text: string, opts?: EnqueueOpts) => {
      const trimmed = text.trim();
      const speakId = opts?.speakId ?? "";
      const utteranceId = opts?.utteranceId ?? "";

      if (opts?.interrupt) {
        stopCompanionSpeech();
        invoke("tts_stop").catch(() => {});
        chainRef.current = Promise.resolve();
        seenSpeakIdsRef.current.clear();
        recentTextRef.current.clear();
        if (!trimmed) return chainRef.current;
      } else if (!trimmed) {
        return chainRef.current;
      }

      if (shouldSkipDuplicate(trimmed, speakId, utteranceId)) {
        void markSpeakDone(speakId);
        return chainRef.current;
      }

      chainRef.current = chainRef.current
        .then(async () => {
          await speakReply(trimmed);
          await markSpeakDone(speakId);
        })
        .catch(async (err) => {
          console.warn("[voice] speak queue failed:", err);
          await markSpeakDone(speakId);
        });

      return chainRef.current;
    },
    [markSpeakDone, shouldSkipDuplicate, speakReply],
  );

  const resetQueue = useCallback(() => {
    stopCompanionSpeech();
    invoke("tts_stop").catch(() => {});
    chainRef.current = Promise.resolve();
    seenSpeakIdsRef.current.clear();
    recentTextRef.current.clear();
  }, []);

  return { enqueueSpeak, resetQueue };
}
