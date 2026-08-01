import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { CompanionStatusOverlay } from "./CompanionStatusOverlay";
import { CompanionAutomationConsent } from "./CompanionAutomationConsent";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { isTauriApp, useCompanionBackendStt } from "./useCompanionBackendStt";
import { CompanionAvatar } from "./avatar/CompanionAvatar";
import type { AgentLifecycle, AvatarMode, SpeechSequenceKey } from "./avatar/types";
import { AVATAR_STATE_LABEL } from "./avatar/types";
import { speakWithLipSync, stopCompanionSpeech, proceduralMouthLevel } from "./avatar/companionTts";
import { ensureSequenceReady } from "./avatar/avatarSequenceRuntime";
import { useLipSyncLevel } from "./avatar/useLipSyncLevel";
import { PushToTalkButton } from "./PushToTalkButton";
import { CompanionWorkspaceBar } from "./CompanionWorkspaceBar";
import { CompanionMentionInput } from "./CompanionMentionInput";
import { parseMentionAttachments } from "./companionMention";
import type { CompanionUploadedImage } from "./companionImage";
import { useCompanionWorkspace } from "./useCompanionWorkspace";
import { useCompanionDrawTools } from "./useCompanionDrawTools";
import { useCompanionWindow, syncCompanionWindowSize } from "./useCompanionWindow";
import { useCompanionExpanded } from "./useCompanionExpanded";
import { useCompanionRelayWatch } from "./useCompanionRelayWatch";
import { useCompanionSpeechQueue } from "./useCompanionSpeechQueue";
import {
  loadVoiceInputMode,
  saveVoiceInputMode,
  type VoiceInputMode,
} from "./voiceInputMode";

type CompanionChatResult = {
  ok: boolean;
  reply: string;
  steps: { step: string; message: string }[];
  task_id: string;
};

type VoiceSpeakEvent = {
  text: string;
  final: boolean;
  interrupt: boolean;
  utterance_id: string;
  speak_id: string;
};

type VoiceTurnDoneEvent = {
  utterance_id: string;
  ok: boolean;
  reply: string;
};

type AgentStartedEvent = {
  task_id: string;
  text: string;
  channel: string;
};

type AutomationConsentEvent = {
  request_id: string;
  scope: string;
  tool: string;
  message: string;
};

const COMPLETED_MS = 1800;
const CALL_GREETING = "你好，我是小绘，有什么可以帮你的吗？";

export function CompanionApp() {
  const [input, setInput] = useState("");
  const [calling, setCalling] = useState(false);
  const [voiceInputMode, setVoiceInputMode] = useState<VoiceInputMode>(loadVoiceInputMode);
  const [pttHolding, setPttHolding] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [speechSequence, setSpeechSequence] = useState<SpeechSequenceKey | null>(null);
  const [lifecycle, setLifecycle] = useState<AgentLifecycle>("resting");
  const [taskHint, setTaskHint] = useState("");
  const [callError, setCallError] = useState("");
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentMessage, setConsentMessage] = useState("");
  const [pendingImages, setPendingImages] = useState<CompanionUploadedImage[]>([]);
  const consentRequestRef = useRef<string | null>(null);
  const processingRef = useRef(false);
  const completedTimerRef = useRef<number | null>(null);
  const activeUtteranceRef = useRef<string | null>(null);
  const { mouthOpen, setLevelFromAudio } = useLipSyncLevel(speaking);
  const { dragHandleProps } = useCompanionWindow();
  const workspaceState = useCompanionWorkspace();
  const { workspace } = workspaceState;
  const drawTools = useCompanionDrawTools();
  const { expanded, toggleExpanded, exitApp, avatarMaxWidth, expandedAvatarMaxWidth } = useCompanionExpanded();

  const isPtt = voiceInputMode === "push_to_talk";
  const sttSessionActive =
    calling &&
    lifecycle !== "executing" &&
    lifecycle !== "waiting" &&
    !speaking;
  const sttListening = isPtt ? pttHolding : sttSessionActive;
  const busy = lifecycle === "waiting" || lifecycle === "executing";

  const clearCompletedTimer = useCallback(() => {
    if (completedTimerRef.current !== null) {
      window.clearTimeout(completedTimerRef.current);
      completedTimerRef.current = null;
    }
  }, []);

  const finishTask = useCallback(
    (ok: boolean) => {
      clearCompletedTimer();
      activeUtteranceRef.current = null;
      if (ok) {
        setLifecycle("completed");
        completedTimerRef.current = window.setTimeout(() => {
          setLifecycle(calling ? "conversation" : "resting");
          completedTimerRef.current = null;
        }, COMPLETED_MS);
      } else {
        setLifecycle(calling ? "conversation" : "resting");
      }
    },
    [calling, clearCompletedTimer],
  );

  useEffect(() => {
    if (expanded) return;
    void syncCompanionWindowSize(calling, Boolean(callError));
  }, [calling, callError, expanded]);

  useEffect(() => {
    document.documentElement.classList.add("companion-html");
    document.documentElement.style.background = "transparent";
    document.body.classList.add("companion-root");
    document.body.style.background = "transparent";
    const root = document.getElementById("root");
    if (root) {
      root.style.background = "transparent";
    }
    return () => {
      document.documentElement.classList.remove("companion-html");
      document.body.classList.remove("companion-root");
      clearCompletedTimer();
    };
  }, [clearCompletedTimer]);

  useEffect(() => {
    if (!isTauriApp()) return;
    void invoke("companion_raise");
    let unlisten: (() => void) | undefined;
    void getCurrentWindow()
      .onFocusChanged(({ payload: focused }) => {
        if (focused) void invoke("companion_raise");
      })
      .then((fn) => {
        unlisten = fn;
      });
    return () => {
      unlisten?.();
    };
  }, []);

  const speakReplyBackend = useCallback(
    async (text: string, sequence: SpeechSequenceKey = "speaking") => {
      await ensureSequenceReady(sequence);
      setSpeechSequence(sequence);
      setSpeaking(true);
      let raf = 0;
      const tick = () => {
        setLevelFromAudio(proceduralMouthLevel());
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      try {
        await invoke("tts_speak", { text });
      } finally {
        cancelAnimationFrame(raf);
        setSpeaking(false);
        setSpeechSequence(null);
        setLevelFromAudio(0);
      }
    },
    [setLevelFromAudio],
  );

  const speakReply = useCallback(
    async (text: string, opts?: { sequence?: SpeechSequenceKey }) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const sequence = opts?.sequence ?? "speaking";
      setSpeechSequence(sequence);
      await ensureSequenceReady(sequence);
      let speakingActive = false;
      try {
        await speakWithLipSync(trimmed, setLevelFromAudio, {
          onStart: () => {
            speakingActive = true;
            setSpeaking(true);
          },
          onStop: () => {
            speakingActive = false;
            setSpeaking(false);
          },
        });
      } catch (err) {
        console.warn("[voice] WebAudio TTS failed, fallback to system playback:", err);
        await speakReplyBackend(trimmed, sequence);
        return;
      } finally {
        if (speakingActive) setSpeaking(false);
        setSpeechSequence(null);
        setLevelFromAudio(0);
      }
    },
    [setLevelFromAudio, speakReplyBackend],
  );

  const { enqueueSpeak, resetQueue } = useCompanionSpeechQueue(speakReply);
  const { monitoring: relayMonitoring, monitorHint } = useCompanionRelayWatch(true);

  const statusHint =
    relayMonitoring &&
    lifecycle !== "executing" &&
    lifecycle !== "waiting" &&
    !speaking &&
    !sttListening
      ? monitorHint || "Cursor 监听中"
      : taskHint;

  const respondAutomationConsent = useCallback(async (granted: boolean) => {
    const requestId = consentRequestRef.current;
    consentRequestRef.current = null;
    setConsentOpen(false);
    setConsentMessage("");
    if (!requestId) return;
    try {
      await invoke("companion_automation_consent_response", {
        requestId,
        granted,
      });
    } catch (err) {
      console.warn("[automation] consent response failed:", err);
    }
  }, []);

  useEffect(() => {
    const unsubs: Array<Promise<() => void>> = [];
    unsubs.push(
      listen<VoiceSpeakEvent>("companion-voice-speak", (ev) => {
        const { text, interrupt, speak_id: speakId, utterance_id: utteranceId } = ev.payload;
        void enqueueSpeak(text, { speakId, utteranceId, interrupt });
      }),
    );
    unsubs.push(
      listen<VoiceTurnDoneEvent>("companion-voice-turn-done", (ev) => {
        const { utterance_id, ok } = ev.payload;
        if (
          activeUtteranceRef.current &&
          utterance_id &&
          activeUtteranceRef.current !== utterance_id
        ) {
          return;
        }
        processingRef.current = false;
        finishTask(ok);
      }),
    );
    unsubs.push(
      listen<{ utterance_id: string; ok: boolean; error?: string }>(
        "companion-voice-utterance-accepted",
        (ev) => {
          const { utterance_id, ok, error } = ev.payload;
          if (utterance_id) {
            activeUtteranceRef.current = utterance_id;
          }
          if (!ok) {
            processingRef.current = false;
            if (error) {
              console.warn("[voice] relay failed:", error);
            }
            finishTask(false);
          }
        },
      ),
    );
    unsubs.push(
      listen<AgentStartedEvent>("companion-agent-started", (ev) => {
        const { text } = ev.payload;
        if (text.trim()) {
          setTaskHint(text.trim());
        }
        if (lifecycle !== "executing" && lifecycle !== "waiting") {
          setLifecycle("executing");
        }
      }),
    );
    unsubs.push(
      listen<AutomationConsentEvent>("companion-automation-consent", (ev) => {
        const { request_id, message } = ev.payload;
        if (!request_id) return;
        consentRequestRef.current = request_id;
        setConsentMessage(
          message.trim() || "Cursor 即将接管鼠标和键盘操作，是否允许？",
        );
        setConsentOpen(true);
      }),
    );
    return () => {
      void Promise.all(unsubs).then((fns) => fns.forEach((fn) => fn()));
    };
  }, [enqueueSpeak, finishTask, lifecycle]);

  const submitVoiceUtterance = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || processingRef.current) return;
      processingRef.current = true;
      clearCompletedTimer();
      setTaskHint(trimmed);
      setLifecycle("waiting");
      setPttHolding(false);
      try {
        await new Promise((r) => window.setTimeout(r, 150));
        setLifecycle("executing");
        const socketOk = await invoke<boolean>("companion_socket_status").catch(() => false);
        if (socketOk) {
          await invoke("companion_voice_stt", { partial: false, text: trimmed });
          return;
        }
        const result = await invoke<CompanionChatResult>("voice_process_utterance", {
          text: trimmed,
        });
        if (result.reply.trim()) {
          await speakReply(result.reply);
        }
        finishTask(result.ok);
        processingRef.current = false;
      } catch {
        finishTask(false);
        processingRef.current = false;
      }
    },
    [clearCompletedTimer, finishTask, speakReply],
  );

  const runAgentTask = useCallback(
    async (
      text: string,
      opts?: { speak?: boolean; imagePaths?: string[]; filePaths?: string[] },
    ) => {
      if (opts?.speak && calling) {
        await submitVoiceUtterance(text);
        return;
      }
      const trimmed = text.trim();
      const imagePaths = (opts?.imagePaths ?? []).filter((p) => p.trim());
      const filePaths = (opts?.filePaths ?? []).filter((p) => p.trim());
      if ((!trimmed && !imagePaths.length && !filePaths.length) || processingRef.current) return;
      processingRef.current = true;
      clearCompletedTimer();
      const hintParts: string[] = [];
      if (trimmed) hintParts.push(trimmed);
      if (filePaths.length) hintParts.push(`${filePaths.length} 个文件`);
      if (imagePaths.length) hintParts.push(`${imagePaths.length} 张图片`);
      setTaskHint(hintParts.join(" · ") || "发送任务");
      setLifecycle("waiting");
      setPttHolding(false);
      try {
        await new Promise((r) => window.setTimeout(r, 150));
        setLifecycle("executing");
        const result = await invoke<CompanionChatResult>("companion_send_message", {
          text: trimmed || "请分析附件并协助 vibe coding",
          imagePaths,
          filePaths,
        });
        finishTask(result.ok);
      } catch {
        finishTask(false);
      } finally {
        processingRef.current = false;
      }
    },
    [calling, clearCompletedTimer, finishTask, submitVoiceUtterance],
  );

  const interruptTts = useCallback(() => {
    resetQueue();
    setSpeaking(false);
    setSpeechSequence(null);
    setLevelFromAudio(0);
  }, [resetQueue, setLevelFromAudio]);

  const useBackendStt = isTauriApp();

  const handleSttError = useCallback((message: string) => {
    if (!calling) return;
    const friendly =
      message === "service-not-allowed"
        ? "桌面端改用系统麦克风识别，请检查麦克风权限"
        : message;
    setCallError(friendly);
  }, [calling]);

  useCompanionBackendStt({
    sessionActive: useBackendStt && sttSessionActive,
    listening: sttListening,
    continuous: !isPtt,
    onFinal: (text) => {
      void runAgentTask(text, { speak: true });
    },
    onError: handleSttError,
    onListeningChange: setListening,
  });

  useSpeechRecognition({
    active: !useBackendStt && sttSessionActive,
    listening: sttListening,
    lang: "zh-CN",
    continuous: !isPtt,
    autoRestart: !isPtt,
    onPartial: (text) => {
      interruptTts();
      if (calling) {
        invoke("companion_voice_stt", { partial: true, text }).catch(() => {});
      }
    },
    onFinal: (text) => {
      void runAgentTask(text, { speak: true });
    },
    onError: (message) => {
      if (calling) {
        handleSttError(message);
      }
    },
    onListeningChange: setListening,
  });

  useEffect(() => {
    if (pttHolding) {
      setCallError("");
    }
  }, [pttHolding]);

  const send = useCallback(async () => {
    const text = input.trim();
    const { filePaths, imagePaths } = parseMentionAttachments(input, workspace, pendingImages);
    if ((!text && !imagePaths.length && !filePaths.length) || busy) return;
    setInput("");
    setPendingImages([]);
    if (calling) {
      await submitVoiceUtterance(text || "请分析附件并协助 vibe coding");
      return;
    }
    await runAgentTask(text, { filePaths, imagePaths });
  }, [input, workspace, pendingImages, busy, calling, runAgentTask, submitVoiceUtterance]);

  const setInputMode = (mode: VoiceInputMode) => {
    setVoiceInputMode(mode);
    saveVoiceInputMode(mode);
    setPttHolding(false);
  };

  const toggleCall = async () => {
    setCallError("");
    try {
      if (calling) {
        resetQueue();
        await invoke("voice_call_stop");
        setCalling(false);
        setPttHolding(false);
        setListening(false);
        setSpeaking(false);
        setSpeechSequence(null);
        setLevelFromAudio(0);
        clearCompletedTimer();
        processingRef.current = false;
        activeUtteranceRef.current = null;
        setLifecycle("resting");
      } else {
        await invoke("voice_call_start");
        setCalling(true);
        setLifecycle("conversation");
        resetQueue();
        void speakReply(CALL_GREETING, { sequence: "greetings" });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : typeof err === "string" ? err : "语音服务不可用";
      setCallError(message.includes("Daemon") ? "后台服务未启动，请重启应用或托盘「重启服务」" : message);
      setCalling(false);
      setLifecycle("resting");
    }
  };

  const avatarMode: AvatarMode = speaking
    ? "speaking"
    : listening
      ? "listening"
      : lifecycle === "executing" || lifecycle === "waiting"
        ? lifecycle
        : relayMonitoring
          ? "monitoring"
          : lifecycle === "conversation"
            ? "conversation"
            : lifecycle;

  return (
    <div
      className={`companion${expanded ? " companion-expanded" : ""}`}
      style={
        expanded
          ? ({
              "--avatar-expanded-scale": Math.max(1.5, avatarMaxWidth / 104),
            } as CSSProperties)
          : undefined
      }
    >
      <div className="avatar-stack">
        <CompanionAutomationConsent
          open={consentOpen}
          message={consentMessage}
          onConfirm={() => void respondAutomationConsent(true)}
          onCancel={() => void respondAutomationConsent(false)}
        />
        <CompanionStatusOverlay
          mode={avatarMode}
          taskHint={statusHint}
          expanded={expanded}
          onToggleExpanded={() => void toggleExpanded()}
          onClose={exitApp}
        />
        <div
          className="avatar-wrap companion-drag-handle"
          aria-label={AVATAR_STATE_LABEL[avatarMode]}
          title="拖拽移动"
          {...dragHandleProps}
        >
          {lifecycle === "completed" ? (
            <div className="companion-speech-bubble" role="status" aria-live="assertive">
              任务完成
            </div>
          ) : null}
          <CompanionAvatar
            mouthOpen={mouthOpen}
            mode={avatarMode}
            maxDisplayWidth={avatarMaxWidth}
            expandedMaxWidth={expandedAvatarMaxWidth}
            speechSequence={speechSequence}
          />
        </div>
      </div>

      <div className="companion-bottom">
        {calling && (
          <div className={`call-tools${expanded ? " call-tools-expanded" : ""}`}>
            <button
              type="button"
              className={`icon-btn ${isPtt ? "active" : ""}`}
              onClick={() => setInputMode("push_to_talk")}
              aria-label="按住说"
              title="按住说"
            >
              PTT
            </button>
            <button
              type="button"
              className={`icon-btn ${!isPtt ? "active" : ""}`}
              onClick={() => setInputMode("continuous")}
              aria-label="自由说"
              title="自由说"
            >
              ∞
            </button>
            {isPtt && (
              <PushToTalkButton
                compact
                holding={pttHolding}
                disabled={busy || speaking}
                onHoldChange={setPttHolding}
              />
            )}
          </div>
        )}

        {callError && !expanded ? (
          <div className="companion-call-error" role="alert">
            {callError}
          </div>
        ) : null}

        <CompanionWorkspaceBar
          images={pendingImages}
          onImagesChange={setPendingImages}
          workspaceState={workspaceState}
          drawTools={drawTools}
        />

        <div className="input-bar">
        <button
          type="button"
          className={`icon-btn phone-btn ${calling ? "active" : ""}`}
          onClick={toggleCall}
          aria-label={calling ? "挂断" : "电话"}
          title={calling ? "挂断" : "电话"}
        >
          {calling ? "✕" : "☎"}
        </button>
        <CompanionMentionInput
          value={input}
          onChange={setInput}
          onSubmit={() => void send()}
          disabled={busy}
          workspace={workspace}
          images={pendingImages}
          placeholder={calling ? "打字发送，输入 @ 引用文件…" : "输入 @ 引用文件或图片，协助 vibe coding…"}
        />
        <button
          type="button"
          className="icon-btn send-btn"
          onClick={send}
          disabled={busy}
          aria-label="发送"
          title="发送"
        >
          ↑
        </button>
      </div>
      </div>
    </div>
  );
}
