type PrepareSequence = (key: string) => Promise<void>;

let prepareSequence: PrepareSequence | null = null;

export function registerSequencePrepare(fn: PrepareSequence | null): void {
  prepareSequence = fn;
}

/** 播报前确保指定序列开头帧已解码，避免有声无画。 */
export async function ensureSequenceReady(key = "speaking"): Promise<void> {
  await prepareSequence?.(key);
}

/** @deprecated use ensureSequenceReady */
export async function ensureSpeakingReady(): Promise<void> {
  await ensureSequenceReady("speaking");
}
