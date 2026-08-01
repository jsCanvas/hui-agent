import { useCallback, useEffect, useRef } from "react";

type Props = {
  disabled?: boolean;
  holding: boolean;
  onHoldChange: (holding: boolean) => void;
  compact?: boolean;
};

export function PushToTalkButton({ disabled, holding, onHoldChange, compact }: Props) {
  const holdRef = useRef(false);

  const startHold = useCallback(() => {
    if (disabled || holdRef.current) return;
    holdRef.current = true;
    onHoldChange(true);
  }, [disabled, onHoldChange]);

  const endHold = useCallback(() => {
    if (!holdRef.current) return;
    holdRef.current = false;
    onHoldChange(false);
  }, [onHoldChange]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (disabled || e.repeat || e.code !== "Space") return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      e.preventDefault();
      startHold();
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      e.preventDefault();
      endHold();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [disabled, startHold, endHold]);

  useEffect(() => {
    return () => {
      if (holdRef.current) {
        holdRef.current = false;
        onHoldChange(false);
      }
    };
  }, [onHoldChange]);

  return (
    <button
      type="button"
      className={compact ? `icon-btn mic-btn ${holding ? "active" : ""}` : `ptt-btn ${holding ? "active" : ""}`}
      disabled={disabled}
      aria-label={holding ? "松开结束" : "按住说话"}
      title={holding ? "松开结束" : "按住说话"}
      onPointerDown={(e) => {
        e.preventDefault();
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        startHold();
      }}
      onPointerUp={(e) => {
        e.preventDefault();
        endHold();
      }}
      onPointerCancel={endHold}
      onLostPointerCapture={endHold}
      onContextMenu={(e) => e.preventDefault()}
    >
      {compact ? "🎤" : holding ? "🎤 松开结束" : "🎤 按住说话"}
      {!compact && <span className="ptt-hint">Space</span>}
    </button>
  );
}
