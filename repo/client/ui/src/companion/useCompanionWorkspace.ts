import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { isTauriApp } from "./useCompanionBackendStt";

type WorkspaceInfo = {
  workspace: string;
  label: string;
};

export function useCompanionWorkspace() {
  const [info, setInfo] = useState<WorkspaceInfo>({
    workspace: "",
    label: "选择工作区",
  });
  const [picking, setPicking] = useState(false);

  const refresh = useCallback(async () => {
    if (!isTauriApp()) return;
    try {
      const next = await invoke<WorkspaceInfo>("get_cursor_workspace");
      setInfo(next);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pickWorkspace = useCallback(async () => {
    if (!isTauriApp() || picking) return;
    setPicking(true);
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "选择项目工作区",
        defaultPath: info.workspace || undefined,
      });
      if (typeof selected !== "string" || !selected.trim()) return;
      const next = await invoke<WorkspaceInfo>("set_cursor_workspace", {
        workspace: selected,
      });
      setInfo(next);
    } catch (err) {
      console.warn("[workspace] pick failed:", err);
    } finally {
      setPicking(false);
    }
  }, [info.workspace, picking]);

  const clearWorkspace = useCallback(async () => {
    if (!isTauriApp()) return;
    try {
      const next = await invoke<WorkspaceInfo>("set_cursor_workspace", { workspace: "" });
      setInfo(next);
    } catch {
      /* ignore */
    }
  }, []);

  return {
    workspace: info.workspace,
    label: info.label,
    picking,
    pickWorkspace,
    clearWorkspace,
    refresh,
    supported: isTauriApp(),
  };
}

export type CompanionWorkspaceState = ReturnType<typeof useCompanionWorkspace>;
