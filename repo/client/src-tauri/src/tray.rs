use std::sync::Arc;

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder,
};

use crate::process::ServiceManager;

async fn run_blocking<T, F>(f: F) -> Result<T, String>
where
    T: Send + 'static,
    F: FnOnce() -> Result<T, String> + Send + 'static,
{
    tokio::task::spawn_blocking(f)
        .await
        .map_err(|e| format!("internal task error: {e}"))?
}

pub fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let show_settings = MenuItem::with_id(app, "show_settings", "打开设置", true, None::<&str>)?;
    let show_companion = MenuItem::with_id(app, "show_companion", "显示助手", true, None::<&str>)?;
    let restart = MenuItem::with_id(app, "restart_services", "重启服务", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &show_settings,
            &show_companion,
            &PredefinedMenuItem::separator(app)?,
            &restart,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    let _tray = TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .tooltip("HuiAgent")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show_settings" => {
                let _ = show_settings_window(app);
            }
            "show_companion" => {
                if let Some(w) = app.get_webview_window("companion") {
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            }
            "restart_services" => {
                if let Some(svc) = app.try_state::<Arc<ServiceManager>>() {
                    let _ = svc.restart_all();
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                let _ = show_settings_window(app);
            }
        })
        .build(app)?;

    Ok(())
}

pub fn show_settings_window(app: &AppHandle) -> Result<(), String> {
    if let Some(w) = app.get_webview_window("settings") {
        w.show().map_err(|e| e.to_string())?;
        w.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }
    WebviewWindowBuilder::new(app, "settings", WebviewUrl::App("index.html".into()))
        .title("HuiAgent 设置")
        .inner_size(760.0, 640.0)
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn app_exit(app: AppHandle) {
    app.exit(0);
}

#[tauri::command]
pub fn companion_reset_position(app: AppHandle) -> Result<(), String> {
    position_companion(&app)
}

pub fn position_companion(app: &AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("companion")
        .ok_or_else(|| "companion window missing".to_string())?;
    if let Ok(monitor) = window.current_monitor() {
        if let Some(m) = monitor {
            let size = m.size();
            let scale = m.scale_factor();
            let win_size = window.outer_size().map_err(|e| e.to_string())?;
            let x = (size.width as f64 / scale - win_size.width as f64 / scale - 12.0) as i32;
            let y = (size.height as f64 / scale - win_size.height as f64 / scale - 16.0) as i32;
            window.set_position(tauri::Position::Logical(tauri::LogicalPosition {
                x: x as f64,
                y: y as f64,
            })).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

#[derive(serde::Serialize)]
pub struct ServiceStatus {
    pub tts_running: bool,
    pub tts_healthy: bool,
    pub daemon_running: bool,
    pub cursor_relay_running: bool,
    pub cursor_online: bool,
    pub socket_running: bool,
    pub socket_host: String,
    pub socket_port: u16,
    pub socket_token: String,
    pub mcp_python: String,
    pub config_path: String,
}

fn read_socket_config() -> (String, u16, String) {
    let path = dirs_config_path();
    if let Ok(text) = std::fs::read_to_string(&path) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
            let sock = &v["socket"];
            let host = sock["host"].as_str().unwrap_or("127.0.0.1").to_string();
            let port = sock["port"].as_u64().unwrap_or(18765) as u16;
            let token = sock["token"].as_str().unwrap_or("").to_string();
            return (host, port, token);
        }
    }
    ("127.0.0.1".into(), 18765, String::new())
}

#[tauri::command]
pub fn get_service_status(services: State<'_, Arc<ServiceManager>>) -> ServiceStatus {
    let config_path = dirs_config_path();
    let (socket_host, socket_port, socket_token) = read_socket_config();
    let socket_running = services
        .daemon_healthy()
        .and_then(|v| v.get("socket").cloned())
        .and_then(|s| s.get("running").and_then(|r| r.as_bool()))
        .unwrap_or(false);
    ServiceStatus {
        tts_running: services.tts_running(),
        tts_healthy: services.tts_healthy(),
        daemon_running: services.daemon_running(),
        cursor_relay_running: services.cursor_relay_running(),
        cursor_online: services.cursor_relay_online(),
        socket_running,
        socket_host,
        socket_port,
        socket_token,
        mcp_python: services.python.display().to_string(),
        config_path,
    }
}

#[tauri::command]
pub fn restart_services(services: State<'_, Arc<ServiceManager>>) -> Result<(), String> {
    services.restart_all()
}

#[tauri::command]
pub fn export_cursor_config(services: State<'_, Arc<ServiceManager>>) -> Result<String, String> {
    let python = services.python.display().to_string();
    let cfg = serde_json::json!({
        "mcpServers": {
            "hui-agent-desktop": {
                "command": python,
                "args": ["-m", "hui_mcp"],
                "env": {
                    "TTS_PROXY_PORT": std::env::var("TTS_PROXY_PORT").unwrap_or_else(|_| "8896".into()),
                    "EDGE_TTS_VOICE": std::env::var("EDGE_TTS_VOICE").unwrap_or_else(|_| "zh-CN-XiaoxiaoNeural".into())
                }
            }
        }
    });
    serde_json::to_string_pretty(&cfg).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn export_socket_info(services: State<'_, Arc<ServiceManager>>) -> Result<String, String> {
    let _ = services;
    let (host, port, token) = read_socket_config();
    let info = serde_json::json!({
        "host": host,
        "port": port,
        "token": token,
        "protocol": "ndjson",
        "auth": {"type": "auth", "token": token},
        "example_tool_invoke": {
            "type": "tool.invoke",
            "id": "1",
            "name": "get_screen_info",
            "arguments": {}
        },
        "skill_doc": "hui-agent/docs/solution/skills/hui-agent-socket-bridge/SKILL.md"
    });
    serde_json::to_string_pretty(&info).map_err(|e| e.to_string())
}

#[derive(serde::Serialize, serde::Deserialize, Clone)]
pub struct AgentStep {
    pub step: String,
    pub message: String,
}

#[derive(serde::Serialize)]
pub struct CompanionChatResult {
    pub ok: bool,
    pub reply: String,
    pub steps: Vec<AgentStep>,
    pub task_id: String,
}

fn daemon_port() -> String {
    std::env::var("HUI_AGENT_DAEMON_PORT").unwrap_or_else(|_| "18766".into())
}

#[tauri::command]
pub async fn companion_relay_status() -> Result<serde_json::Value, String> {
    let health = daemon_get("/health").await?;
    let agent = health
        .get("agent")
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    Ok(serde_json::json!({
        "ok": health.get("ok").and_then(|v| v.as_bool()).unwrap_or(false),
        "cursor_online": agent.get("cursor_online").and_then(|v| v.as_bool()).unwrap_or(false),
        "companion_online": agent.get("companion_online").and_then(|v| v.as_bool()).unwrap_or(false),
        "cursor_waiting": agent.get("cursor_waiting").and_then(|v| v.as_bool()).unwrap_or(false),
        "watch_remaining_sec": agent.get("watch_remaining_sec"),
    }))
}

async fn daemon_post(path: &str, body: serde_json::Value) -> Result<serde_json::Value, String> {
    let port = daemon_port();
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .post(format!("http://127.0.0.1:{port}{path}"))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Agent 服务不可用，请确认后台 Daemon 已启动：{e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Daemon HTTP {} {}", path, resp.status()));
    }
    resp.json().await.map_err(|e| e.to_string())
}

async fn daemon_get(path: &str) -> Result<serde_json::Value, String> {
    let port = daemon_port();
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .get(format!("http://127.0.0.1:{port}{path}"))
        .send()
        .await
        .map_err(|e| format!("Agent 服务不可用，请确认后台 Daemon 已启动：{e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Daemon HTTP GET {} {}", path, resp.status()));
    }
    resp.json().await.map_err(|e| e.to_string())
}

fn parse_agent_result(v: serde_json::Value) -> Result<CompanionChatResult, String> {
    let steps = v
        .get("steps")
        .and_then(|s| s.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|item| {
                    Some(AgentStep {
                        step: item.get("step")?.as_str()?.to_string(),
                        message: item.get("message")?.as_str()?.to_string(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    Ok(CompanionChatResult {
        ok: v.get("ok").and_then(|x| x.as_bool()).unwrap_or(false),
        reply: v
            .get("reply")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
        steps,
        task_id: v
            .get("task_id")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string(),
    })
}

#[tauri::command]
pub async fn companion_send_message(
    text: String,
    services: State<'_, Arc<ServiceManager>>,
    app: AppHandle,
) -> Result<CompanionChatResult, String> {
    let _ = services;
    app.emit("companion-task", &text).ok();
    let v = daemon_post("/agent/chat", serde_json::json!({ "text": text })).await?;
    parse_agent_result(v)
}

#[tauri::command]
pub async fn voice_process_utterance(text: String) -> Result<CompanionChatResult, String> {
    let v = daemon_post(
        "/voice/utterance",
        serde_json::json!({ "text": text, "speak": false }),
    )
    .await?;
    parse_agent_result(v)
}

#[tauri::command]
pub async fn companion_stt_start(continuous: bool) -> Result<serde_json::Value, String> {
    daemon_post(
        "/voice/stt/start",
        serde_json::json!({
            "language": "zh-CN",
            "continuous": continuous
        }),
    )
    .await
}

#[tauri::command]
pub async fn companion_stt_stop() -> Result<serde_json::Value, String> {
    daemon_post("/voice/stt/stop", serde_json::json!({})).await
}

#[tauri::command]
pub async fn companion_stt_poll() -> Result<serde_json::Value, String> {
    daemon_get("/voice/stt/poll").await
}

#[tauri::command]
pub async fn voice_call_start(services: State<'_, Arc<ServiceManager>>) -> Result<(), String> {
    let svc = services.inner().clone();
    run_blocking(move || svc.ensure_tts()).await?;

    let body = serde_json::json!({ "background_listen": false });
    match daemon_post("/voice/start", body.clone()).await {
        Ok(_) => Ok(()),
        Err(e) if e.contains("Agent 服务不可用") || e.contains("daemon unreachable") => {
            let svc = services.inner().clone();
            run_blocking(move || {
                svc.restart_all()?;
                std::thread::sleep(std::time::Duration::from_millis(800));
                Ok(())
            })
            .await?;
            daemon_post("/voice/start", body).await.map(|_| ())
        }
        Err(e) => Err(e),
    }
}

#[tauri::command]
pub async fn voice_call_stop() -> Result<(), String> {
    daemon_post("/voice/stop", serde_json::json!({})).await.map(|_| ())
}

#[tauri::command]
pub async fn tts_stop() -> Result<(), String> {
    daemon_post("/voice/tts/stop", serde_json::json!({})).await.map(|_| ())
}

#[tauri::command]
pub async fn tts_speak(
    text: String,
    services: State<'_, Arc<ServiceManager>>,
) -> Result<String, String> {
    let svc = services.inner().clone();
    run_blocking(move || svc.ensure_tts()).await?;

    let port = std::env::var("TTS_PROXY_PORT").unwrap_or_else(|_| "8896".into());
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("http://127.0.0.1:{port}/tts"))
        .json(&serde_json::json!({
            "text": text,
            "voice": std::env::var("EDGE_TTS_VOICE").unwrap_or_else(|_| "zh-CN-XiaoxiaoNeural".into()),
            "rate": "+10%",
            "pitch": "+2Hz"
        }))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("TTS HTTP {}", resp.status()));
    }
    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
    let tmp = std::env::temp_dir().join(format!("hui-tts-{}.mp3", uuid_simple()));
    std::fs::write(&tmp, &bytes).map_err(|e| e.to_string())?;
    let tmp_path = tmp.clone();
    run_blocking(move || play_mp3(&tmp_path)).await?;
    Ok(format!("spoken {} bytes", bytes.len()))
}

fn play_mp3(path: &std::path::Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("afplay")
            .arg(path)
            .status()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        let p = path.display();
        std::process::Command::new("powershell")
            .args([
                "-c",
                &format!("(New-Object Media.SoundPlayer '{p}').PlaySync()"),
            ])
            .status()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    #[allow(unreachable_code)]
    Err("unsupported platform for mp3 playback".into())
}

fn dirs_config_path() -> String {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| "~".into());
    format!("{home}/.hui-agent/config.json")
}

fn uuid_simple() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}
