import { useCallback, useEffect, useRef, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import type { CompanionUploadedImage } from "./companionImage";

type Props = {
  images: CompanionUploadedImage[];
  onRemove: (path: string) => void;
  uploading: boolean;
  onPick: () => void;
};

function ImageIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden fill="none">
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="9" cy="10" r="1.8" fill="currentColor" />
      <path
        d="M6 17l4.5-4.5a1 1 0 0 1 1.4 0L16 16.6l2-2a1 1 0 0 1 1.4 0L21 16"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CompanionUploadedImagePanel({ images, onRemove, uploading, onPick }: Props) {
  const [panelOpen, setPanelOpen] = useState(false);
  const hideTimerRef = useRef<number | null>(null);
  const count = images.length;

  useEffect(() => {
    if (count === 0) setPanelOpen(false);
  }, [count]);

  const openPanel = useCallback(() => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (count > 0) setPanelOpen(true);
  }, [count]);

  const closePanel = useCallback(() => {
    hideTimerRef.current = window.setTimeout(() => {
      setPanelOpen(false);
      hideTimerRef.current = null;
    }, 120);
  }, []);

  return (
    <div
      className="workspace-image-wrap"
      onMouseEnter={openPanel}
      onMouseLeave={closePanel}
    >
      {panelOpen && count > 0 ? (
        <div className="workspace-image-panel" role="list" aria-label="已上传图片">
          <div className="workspace-image-panel-head">
            <span>已上传 {count} 张</span>
          </div>
          <ul className="workspace-image-list">
            {images.map((img) => (
              <li key={img.path} className="workspace-image-item">
                <img
                  className="workspace-image-thumb"
                  src={convertFileSrc(img.path)}
                  alt=""
                  loading="lazy"
                />
                <span className="workspace-image-name" title={img.name}>
                  {img.name}
                </span>
                <button
                  type="button"
                  className="workspace-image-remove"
                  aria-label={`删除 ${img.name}`}
                  title="删除"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(img.path);
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <button
        type="button"
        className={`workspace-image-btn${count > 0 ? " active" : ""}`}
        onClick={() => void onPick()}
        disabled={uploading}
        aria-label={count > 0 ? `已选 ${count} 张图片，继续上传` : "上传图片"}
        title={count > 0 ? `已选 ${count} 张图片，悬停查看` : "上传图片"}
      >
        <ImageIcon />
        {count > 0 ? (
          <span className="workspace-image-badge" aria-hidden>
            {count > 99 ? "99+" : count}
          </span>
        ) : null}
      </button>
    </div>
  );
}
