//! Spawn and supervise Python backend services (TTS proxy + capture daemon + Cursor relay).

use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

pub struct ServiceManager {
    pub mcp_server_dir: PathBuf,
    pub client_root: PathBuf,
    pub python: PathBuf,
    tts: Mutex<Option<Child>>,
    daemon: Mutex<Option<Child>>,
    cursor_relay: Mutex<Option<Child>>,
}

impl ServiceManager {
    pub fn new() -> Result<Self, String> {
        let mcp_server_dir = resolve_mcp_server_dir()?;
        let client_root = mcp_server_dir
            .parent()
            .ok_or_else(|| "invalid mcp-server path".to_string())?
            .to_path_buf();
        let python = resolve_python(&mcp_server_dir)?;
        Ok(Self {
            mcp_server_dir,
            client_root,
            python,
            tts: Mutex::new(None),
            daemon: Mutex::new(None),
            cursor_relay: Mutex::new(None),
        })
    }

    pub fn start_all(&self) -> Result<(), String> {
        self.start_tts()?;
        self.start_daemon()?;
        self.wait_daemon_healthy(15)?;
        Ok(())
    }

    pub fn stop_all(&self) {
        self.stop_child(&self.cursor_relay);
        self.stop_child(&self.daemon);
        self.stop_child(&self.tts);
    }

    pub fn restart_all(&self) -> Result<(), String> {
        self.stop_all();
        kill_orphan_backend_processes();
        std::thread::sleep(Duration::from_millis(500));
        self.start_all()
    }

    /// Keep Cursor Socket relay alive while daemon is running.
    pub fn ensure_cursor_relay(&self) {
        if self.cursor_relay_online() {
            return;
        }
        if self.is_running(&self.cursor_relay) {
            return;
        }
        if self.daemon_healthy().is_none() {
            return;
        }
        let _ = self.start_cursor_relay();
    }

    pub fn start_watchdog(self: &std::sync::Arc<Self>) {
        let svc = self.clone();
        std::thread::spawn(move || loop {
            std::thread::sleep(Duration::from_secs(8));
            svc.ensure_daemon();
            let _ = svc.ensure_tts();
            svc.ensure_cursor_relay();
        });
    }

    fn ensure_daemon(&self) {
        if self.daemon_healthy().is_some() {
            return;
        }
        if self.is_running(&self.daemon) {
            return;
        }
        let _ = self.start_daemon();
    }

    pub fn tts_running(&self) -> bool {
        self.is_running(&self.tts)
    }

    pub fn daemon_running(&self) -> bool {
        self.is_running(&self.daemon)
    }

    pub fn cursor_relay_running(&self) -> bool {
        self.is_running(&self.cursor_relay) || self.cursor_relay_online()
    }

    pub fn tts_healthy(&self) -> bool {
        let port = tts_port();
        let url = format!("http://127.0.0.1:{port}/health");
        let client = match reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
        {
            Ok(c) => c,
            Err(_) => return false,
        };
        client
            .get(&url)
            .send()
            .ok()
            .and_then(|r| {
                if !r.status().is_success() {
                    return None;
                }
                r.json::<serde_json::Value>().ok()
            })
            .and_then(|v| v.get("ok").and_then(|x| x.as_bool()))
            .unwrap_or(false)
    }

    pub fn ensure_tts(&self) -> Result<(), String> {
        if self.tts_healthy() {
            return Ok(());
        }
        self.stop_child(&self.tts);
        kill_listeners_on_port(&tts_port());
        std::thread::sleep(Duration::from_millis(300));
        self.start_tts()?;
        for _ in 0..20 {
            if self.tts_healthy() {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        Err("TTS 服务不可用，请检查网络或重启应用".into())
    }

    pub fn daemon_healthy(&self) -> Option<serde_json::Value> {
        let port = std::env::var("HUI_AGENT_DAEMON_PORT").unwrap_or_else(|_| "18766".into());
        let url = format!("http://127.0.0.1:{port}/health");
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .ok()?;
        let resp = client.get(&url).send().ok()?;
        if !resp.status().is_success() {
            return None;
        }
        resp.json().ok()
    }

    pub fn cursor_relay_online(&self) -> bool {
        self.daemon_healthy()
            .and_then(|v| v.get("agent").cloned())
            .and_then(|a| a.get("cursor_online").and_then(|x| x.as_bool()))
            .unwrap_or(false)
    }

    pub fn start_tts(&self) -> Result<(), String> {
        if self.tts_healthy() {
            return Ok(());
        }
        self.stop_child(&self.tts);
        kill_listeners_on_port(&tts_port());
        let mut cmd = Command::new(&self.python);
        cmd.current_dir(&self.mcp_server_dir)
            .args(["-m", "hui_mcp.voice.tts_proxy"])
            .env(
                "TTS_PROXY_PORT",
                std::env::var("TTS_PROXY_PORT").unwrap_or_else(|_| "8896".into()),
            )
            .env(
                "EDGE_TTS_VOICE",
                std::env::var("EDGE_TTS_VOICE").unwrap_or_else(|_| "zh-CN-XiaoxiaoNeural".into()),
            )
            .stdout(Stdio::null())
            .stderr(Stdio::inherit());
        let child = cmd.spawn().map_err(|e| format!("start tts proxy: {e}"))?;
        *self.tts.lock().unwrap() = Some(child);
        Ok(())
    }

    fn start_daemon(&self) -> Result<(), String> {
        if self.is_running(&self.daemon) {
            return Ok(());
        }
        if self.daemon_healthy().is_some() {
            return Ok(());
        }
        let mut cmd = Command::new(&self.python);
        cmd.current_dir(&self.mcp_server_dir)
            .args(["-m", "hui_mcp.daemon"])
            .stdout(Stdio::null())
            .stderr(Stdio::inherit());
        let child = cmd.spawn().map_err(|e| format!("start daemon: {e}"))?;
        *self.daemon.lock().unwrap() = Some(child);
        Ok(())
    }

    fn start_cursor_relay(&self) -> Result<(), String> {
        if self.cursor_relay_online() {
            return Ok(());
        }
        if self.is_running(&self.cursor_relay) {
            return Ok(());
        }

        let script = self
            .client_root
            .join("scripts")
            .join("cursor-socket-client.py");
        if !script.exists() {
            return Err(format!("missing cursor relay script: {}", script.display()));
        }

        let mut cmd = Command::new(&self.python);
        cmd.current_dir(&self.client_root)
            .arg(&script)
            .stdout(Stdio::null())
            .stderr(Stdio::inherit());
        let child = cmd.spawn().map_err(|e| format!("start cursor relay: {e}"))?;
        *self.cursor_relay.lock().unwrap() = Some(child);
        Ok(())
    }

    fn wait_daemon_healthy(&self, timeout_sec: u64) -> Result<(), String> {
        let attempts = timeout_sec * 5;
        for _ in 0..attempts {
            if self.daemon_healthy().is_some() {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        Err("daemon health check timeout".into())
    }

    fn stop_child(&self, slot: &Mutex<Option<Child>>) {
        let mut guard = slot.lock().unwrap();
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    fn is_running(&self, slot: &Mutex<Option<Child>>) -> bool {
        let mut guard = slot.lock().unwrap();
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(Some(_)) => {
                    *guard = None;
                    false
                }
                Ok(None) => true,
                Err(_) => false,
            }
        } else {
            false
        }
    }
}

fn resolve_mcp_server_dir() -> Result<PathBuf, String> {
    if let Ok(p) = std::env::var("HUI_AGENT_MCP_DIR") {
        let path = PathBuf::from(p);
        if path.exists() {
            return Ok(path);
        }
    }
    let mut dir = std::env::current_dir().map_err(|e| e.to_string())?;
    for _ in 0..6 {
        let candidate = dir.join("mcp-server");
        if candidate.join("hui_mcp").exists() {
            return Ok(candidate);
        }
        if !dir.pop() {
            break;
        }
    }
    Err("找不到 mcp-server 目录，请设置 HUI_AGENT_MCP_DIR".into())
}

fn resolve_python(mcp_server_dir: &Path) -> Result<PathBuf, String> {
    let venv_py = mcp_server_dir.join(".venv/bin/python");
    if venv_py.exists() {
        return Ok(venv_py);
    }
    let venv_py_win = mcp_server_dir.join(".venv/Scripts/python.exe");
    if venv_py_win.exists() {
        return Ok(venv_py_win);
    }
    if let Ok(p) = std::env::var("HUI_AGENT_PYTHON") {
        return Ok(PathBuf::from(p));
    }
    Ok(PathBuf::from("python3"))
}

#[cfg(unix)]
fn kill_orphan_backend_processes() {
    for pattern in [
        "cursor-socket-client.py",
        "hui_mcp.daemon",
        "hui_mcp.voice.tts_proxy",
    ] {
        let _ = Command::new("pkill")
            .args(["-f", pattern])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

#[cfg(not(unix))]
fn kill_orphan_backend_processes() {}

fn tts_port() -> String {
    std::env::var("TTS_PROXY_PORT").unwrap_or_else(|_| "8896".into())
}

#[cfg(unix)]
fn kill_listeners_on_port(port: &str) {
    let output = Command::new("lsof")
        .args(["-ti", &format!(":{port}")])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output();
    if let Ok(out) = output {
        for pid in String::from_utf8_lossy(&out.stdout).lines() {
            let pid = pid.trim();
            if pid.is_empty() {
                continue;
            }
            let _ = Command::new("kill")
                .arg(pid)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }
}

#[cfg(not(unix))]
fn kill_listeners_on_port(_port: &str) {}
