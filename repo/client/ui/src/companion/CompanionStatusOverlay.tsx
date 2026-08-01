import type { AvatarMode } from "./avatar/types";
import { AVATAR_STATE_LABEL } from "./avatar/types";

type Props = {
  mode: AvatarMode;
  taskHint?: string;
  expanded?: boolean;
  onToggleExpanded?: () => void;
  onClose?: () => void;
};

function statusClass(mode: AvatarMode): string {
  if (mode === "executing" || mode === "waiting") return "is-busy";
  if (mode === "completed") return "is-completed";
  if (mode === "speaking" || mode === "listening") return "is-voice";
  if (mode === "monitoring") return "is-monitoring";
  return "";
}

function ExpandIcon({ shrink }: { shrink?: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
      {shrink ? (
        <>
          <path
            d="M4 1H1v3M8 1h3v3M4 11H1V8M8 11h3V8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      ) : (
        <>
          <path
            d="M1 4V1h3M11 4V1H8M1 8v3h3M11 8v3H8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
      <path
        d="M2.5 2.5l7 7M9.5 2.5l-7 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function CompanionStatusOverlay({
  mode,
  taskHint,
  expanded = false,
  onToggleExpanded,
  onClose,
}: Props) {
  const label = AVATAR_STATE_LABEL[mode];
  const detail =
    taskHint &&
    (mode === "waiting" || mode === "executing" || mode === "monitoring")
      ? taskHint.length > 14
        ? `${taskHint.slice(0, 14)}…`
        : taskHint
      : null;

  return (
    <div className="companion-status-row">
      <button
        type="button"
        className="companion-chrome-btn companion-chrome-btn-close"
        onClick={onClose}
        aria-label="关闭"
        title="关闭"
      >
        <CloseIcon />
      </button>
      <div className={`companion-status-pill ${statusClass(mode)}`} aria-live="polite">
        <span className="companion-status-label">{label}</span>
        {detail ? <span className="companion-status-detail">{detail}</span> : null}
      </div>
      <button
        type="button"
        className="companion-chrome-btn"
        onClick={onToggleExpanded}
        aria-label={expanded ? "缩小" : "放大"}
        title={expanded ? "缩小" : "放大"}
      >
        <ExpandIcon shrink={expanded} />
      </button>
    </div>
  );
}
