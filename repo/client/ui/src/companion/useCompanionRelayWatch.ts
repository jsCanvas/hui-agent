import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

type RelayStatus = {
  ok?: boolean;
  cursor_waiting?: boolean;
  watch_remaining_sec?: number | null;
};

type WaitEvent = {
  waiting: boolean;
  remaining_sec?: number | null;
};

function formatWatchRemaining(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return "Cursor 监听中";
  if (sec >= 3600) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return m > 0 ? `监听中 · 剩余 ${h}h${m}m` : `监听中 · 剩余 ${h}h`;
  }
  if (sec >= 60) {
    return `监听中 · 剩余 ${Math.floor(sec / 60)}m`;
  }
  return `监听中 · 剩余 ${sec}s`;
}

/** Cursor companion_socket_wait 监听状态（Socket 事件 + 轮询 health）。 */
export function useCompanionRelayWatch(enabled = true) {
  const [monitoring, setMonitoring] = useState(false);
  const [monitorHint, setMonitorHint] = useState("");

  useEffect(() => {
    if (!enabled) {
      setMonitoring(false);
      setMonitorHint("");
      return;
    }

    let cancelled = false;

    const apply = (waiting: boolean, remainingSec?: number | null) => {
      setMonitoring(waiting);
      setMonitorHint(waiting ? formatWatchRemaining(remainingSec) : "");
    };

    const poll = async () => {
      try {
        const data = await invoke<RelayStatus>("companion_relay_status");
        if (cancelled) return;
        apply(Boolean(data.cursor_waiting), data.watch_remaining_sec);
      } catch {
        if (!cancelled) apply(false);
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 4000);

    const unsubs: Array<Promise<() => void>> = [];
    unsubs.push(
      listen<WaitEvent>("companion-agent-wait", (ev) => {
        apply(ev.payload.waiting, ev.payload.remaining_sec);
      }),
    );

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      void Promise.all(unsubs).then((fns) => fns.forEach((fn) => fn()));
    };
  }, [enabled]);

  return { monitoring, monitorHint };
}
