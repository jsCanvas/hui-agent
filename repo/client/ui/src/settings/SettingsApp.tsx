import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type ServiceStatus = {
  tts_running: boolean;
  tts_healthy: boolean;
  daemon_running: boolean;
  socket_running: boolean;
  socket_host: string;
  socket_port: number;
  socket_token: string;
  mcp_python: string;
  config_path: string;
};

export function SettingsApp() {
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [cursorConfig, setCursorConfig] = useState("");
  const [socketInfo, setSocketInfo] = useState("");

  const refresh = useCallback(async () => {
    const s = await invoke<ServiceStatus>("get_service_status");
    setStatus(s);
    setCursorConfig(await invoke<string>("export_cursor_config"));
    setSocketInfo(await invoke<string>("export_socket_info"));
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const restart = async () => {
    await invoke("restart_services");
    await refresh();
  };

  const copy = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    alert(`已复制${label}`);
  };

  return (
    <div className="settings">
      <h1>HuiAgent 设置</h1>
      <div className="status-card">
        <h3>服务状态</h3>
        {status ? (
          <>
            <div className="status-row">
              <span>Edge TTS Proxy</span>
              <span className={`badge ${status.tts_healthy ? "ok" : "err"}`}>
                {status.tts_running ? (status.tts_healthy ? "运行中" : "异常") : "已停止"}
              </span>
            </div>
            <div className="status-row">
              <span>后台 Daemon</span>
              <span className={`badge ${status.daemon_running ? "ok" : "err"}`}>
                {status.daemon_running ? "运行中" : "已停止"}
              </span>
            </div>
            <div className="status-row">
              <span>Socket Bridge</span>
              <span className={`badge ${status.socket_running ? "ok" : "err"}`}>
                {status.socket_running
                  ? `${status.socket_host}:${status.socket_port}`
                  : "未就绪"}
              </span>
            </div>
            <div className="status-row">
              <span>Python</span>
              <code style={{ fontSize: 12 }}>{status.mcp_python}</code>
            </div>
          </>
        ) : (
          <p>加载中…</p>
        )}
        <button onClick={restart}>重启服务</button>
        <button onClick={refresh}>刷新</button>
      </div>
      <div className="status-card">
        <h3>Socket Bridge（Agent 实时连接）</h3>
        <pre>{socketInfo}</pre>
        <button onClick={() => copy(socketInfo, "Socket 连接信息")}>复制</button>
      </div>
      <div className="status-card">
        <h3>Cursor MCP 配置</h3>
        <pre>{cursorConfig}</pre>
        <button onClick={() => copy(cursorConfig, "Cursor MCP 配置")}>复制配置</button>
      </div>
    </div>
  );
}
