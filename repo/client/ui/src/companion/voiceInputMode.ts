export type VoiceInputMode = "continuous" | "push_to_talk";

const STORAGE_KEY = "hui-agent-voice-input-mode";

export function loadVoiceInputMode(): VoiceInputMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "continuous" || v === "push_to_talk") return v;
  } catch {
    /* ignore */
  }
  return "push_to_talk";
}

export function saveVoiceInputMode(mode: VoiceInputMode) {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}
