import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { CompanionUploadedImage } from "./companionImage";
import { buildMentionInsert, type MentionOption } from "./companionMention";
import { isTauriApp } from "./useCompanionBackendStt";

type WorkspaceMentionFile = {
  path: string;
  rel: string;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  workspace: string;
  images: CompanionUploadedImage[];
};

export function CompanionMentionInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  workspace,
  images,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionStart, setMentionStart] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [fileHits, setFileHits] = useState<WorkspaceMentionFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesFetched, setFilesFetched] = useState(false);

  const imageOptions = useMemo((): MentionOption[] => {
    const q = mentionQuery.toLowerCase();
    return images
      .filter((img) => !q || img.name.toLowerCase().includes(q))
      .map((img) => ({
        kind: "image" as const,
        path: img.path,
        name: img.name,
        label: img.name,
      }));
  }, [images, mentionQuery]);

  useEffect(() => {
    if (!mentionOpen || !isTauriApp()) {
      setFileHits([]);
      setFilesFetched(false);
      setFilesLoading(false);
      return;
    }
    let cancelled = false;
    setFilesLoading(true);
    void invoke<WorkspaceMentionFile[]>("list_workspace_mention_files", {
      query: mentionQuery,
      limit: 16,
    })
      .then((rows) => {
        if (!cancelled) setFileHits(rows);
      })
      .catch(() => {
        if (!cancelled) setFileHits([]);
      })
      .finally(() => {
        if (!cancelled) {
          setFilesLoading(false);
          setFilesFetched(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mentionOpen, mentionQuery, workspace]);

  const options = useMemo((): MentionOption[] => {
    const files: MentionOption[] = fileHits.map((f) => ({
      kind: "file",
      rel: f.rel,
      path: f.path,
      label: f.rel,
    }));
    return [...imageOptions, ...files];
  }, [fileHits, imageOptions]);

  useEffect(() => {
    setActiveIndex(0);
  }, [mentionQuery, options.length]);

  const syncMentionState = useCallback(
    (nextValue: string, cursor: number) => {
      const before = nextValue.slice(0, cursor);
      const match = before.match(/@([^\s@]*)$/);
      if (!match) {
        setMentionOpen(false);
        setMentionQuery("");
        return;
      }
      setMentionOpen(true);
      setMentionQuery(match[1]);
      setMentionStart(cursor - match[0].length);
    },
    [],
  );

  const handleChange = (next: string) => {
    onChange(next);
    const cursor = inputRef.current?.selectionStart ?? next.length;
    syncMentionState(next, cursor);
  };

  const pickOption = (option: MentionOption) => {
    const input = inputRef.current;
    const cursor = input?.selectionStart ?? value.length;
    const before = value.slice(0, mentionStart);
    const after = value.slice(cursor);
    const insert = buildMentionInsert(option);
    const next = `${before}${insert} ${after}`;
    onChange(next);
    setMentionOpen(false);
    setMentionQuery("");
    window.requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      const pos = before.length + insert.length + 1;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (mentionOpen && options.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % options.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + options.length) % options.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        pickOption(options[activeIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setMentionOpen(false);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  const showHint =
    mentionOpen &&
    mentionQuery.length === 0 &&
    filesFetched &&
    !filesLoading &&
    !workspace.trim() &&
    fileHits.length === 0 &&
    imageOptions.length === 0;

  return (
    <div className="mention-input-wrap">
      {mentionOpen ? (
        <div className="mention-popover" ref={listRef} role="listbox">
          {showHint ? (
            <div className="mention-empty">请先选择工作区，再 @ 引用项目文件</div>
          ) : null}
          {!showHint && filesLoading ? (
            <div className="mention-empty">加载工作区文件…</div>
          ) : null}
          {!showHint && !filesLoading && options.length === 0 ? (
            <div className="mention-empty">无匹配文件或图片</div>
          ) : null}
          {options.map((option, index) => (
            <button
              key={`${option.kind}-${option.kind === "file" ? option.path : option.path}`}
              type="button"
              className={`mention-item${index === activeIndex ? " active" : ""}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pickOption(option)}
            >
              <span className={`mention-kind mention-kind-${option.kind}`}>
                {option.kind === "image" ? "图" : "文件"}
              </span>
              <span className="mention-label">{option.label}</span>
            </button>
          ))}
        </div>
      ) : null}
      <input
        ref={inputRef}
        value={value}
        disabled={disabled}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onClick={(e) =>
          syncMentionState(value, (e.target as HTMLInputElement).selectionStart ?? value.length)
        }
        onKeyUp={(e) =>
          syncMentionState(value, (e.target as HTMLInputElement).selectionStart ?? value.length)
        }
        placeholder={placeholder}
        aria-label="任务输入"
      />
    </div>
  );
}
