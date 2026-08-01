import type { CompanionUploadedImage } from "./companionImage";
import { CompanionUploadedImagePanel } from "./CompanionUploadedImagePanel";
import { useCompanionImageUpload } from "./useCompanionImageUpload";
import type { CompanionWorkspaceState } from "./useCompanionWorkspace";
import type { useCompanionDrawTools } from "./useCompanionDrawTools";

type DrawTools = ReturnType<typeof useCompanionDrawTools>;

type Props = {
  images: CompanionUploadedImage[];
  onImagesChange: (images: CompanionUploadedImage[]) => void;
  workspaceState: CompanionWorkspaceState;
  drawTools: DrawTools;
};

function BrushIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden fill="none">
      <path
        d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="m13.5 6.5 4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function EraserIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden fill="none">
      <path
        d="M21 21l-4.35-4.35M8.5 19.5 3 14l9.5-9.5a2.1 2.1 0 0 1 3 0l4.5 4.5a2.1 2.1 0 0 1 0 3L8.5 19.5z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CompanionWorkspaceBar({
  images,
  onImagesChange,
  workspaceState,
  drawTools,
}: Props) {
  const { workspace, label, picking, pickWorkspace, clearWorkspace, supported } = workspaceState;
  const { uploading, pickImage, removeImage, supported: imageSupported } = useCompanionImageUpload(
    images,
    onImagesChange,
  );
  const { brushActive, toggleBrush, clearDrawings, supported: drawSupported } = drawTools;

  if (!supported && !imageSupported && !drawSupported) return null;

  return (
    <div className="workspace-bar">
      {supported ? (
        <div className="workspace-picker">
          <button
            type="button"
            className="workspace-btn"
            onClick={() => void pickWorkspace()}
            disabled={picking}
            title={workspace || "选择项目目录作为 Cursor 工作区"}
            aria-label="选择工作区"
          >
            <span className="workspace-btn-icon" aria-hidden>
              📁
            </span>
            <span className="workspace-btn-label">{picking ? "选择中…" : label}</span>
          </button>
          {workspace ? (
            <button
              type="button"
              className="workspace-clear"
              onClick={() => void clearWorkspace()}
              aria-label="清除工作区"
              title="清除工作区"
            >
              ×
            </button>
          ) : null}
        </div>
      ) : null}
      {drawSupported ? (
        <div className="workspace-tools">
          <button
            type="button"
            className={`workspace-tool-btn${brushActive ? " active" : ""}`}
            onClick={() => void toggleBrush()}
            aria-label={brushActive ? "关闭画笔" : "画笔标注"}
            title={brushActive ? "关闭画笔" : "画笔标注"}
          >
            <BrushIcon />
          </button>
          <button
            type="button"
            className="workspace-tool-btn"
            onClick={() => void clearDrawings()}
            aria-label="橡皮擦清除"
            title="橡皮擦清除"
          >
            <EraserIcon />
          </button>
        </div>
      ) : null}
      {imageSupported ? (
        <CompanionUploadedImagePanel
          images={images}
          onRemove={removeImage}
          uploading={uploading}
          onPick={pickImage}
        />
      ) : null}
    </div>
  );
}
