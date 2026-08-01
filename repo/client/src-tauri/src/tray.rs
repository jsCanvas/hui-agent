use std::sync::Arc;

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, State, WebviewUrl,
    WebviewWindow, WebviewWindowBuilder,
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

fn read_config_json() -> serde_json::Value {
    let path = dirs_config_path();
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_else(|| serde_json::json!({}))
}

fn write_config_json(mut value: serde_json::Value) -> Result<(), String> {
    let path = dirs_config_path();
    if let Some(parent) = std::path::Path::new(&path).parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    if value.get("cursor").is_none() {
        value["cursor"] = serde_json::json!({});
    }
    let text = serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())
}

fn read_cursor_workspace() -> String {
    read_config_json()["cursor"]["workspace"]
        .as_str()
        .unwrap_or("")
        .to_string()
}

#[derive(serde::Serialize)]
pub struct CursorWorkspaceInfo {
    pub workspace: String,
    pub label: String,
}

#[tauri::command]
pub fn get_cursor_workspace() -> CursorWorkspaceInfo {
    let workspace = read_cursor_workspace();
    CursorWorkspaceInfo {
        label: workspace_label(&workspace),
        workspace,
    }
}

#[tauri::command]
pub fn set_cursor_workspace(workspace: String) -> Result<CursorWorkspaceInfo, String> {
    let workspace = workspace.trim().to_string();
    let mut cfg = read_config_json();
    if cfg.get("cursor").is_none() {
        cfg["cursor"] = serde_json::json!({});
    }
    cfg["cursor"]["workspace"] = serde_json::Value::String(workspace.clone());
    write_config_json(cfg)?;
    Ok(CursorWorkspaceInfo {
        label: workspace_label(&workspace),
        workspace,
    })
}

fn workspace_label(path: &str) -> String {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return "选择工作区".into();
    }
    std::path::Path::new(trimmed)
        .file_name()
        .and_then(|name| name.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| trimmed.to_string())
}

fn uploads_dir() -> Result<std::path::PathBuf, String> {
    let workspace = read_cursor_workspace();
    let base = if workspace.trim().is_empty() {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .map_err(|_| "HOME not set".to_string())?;
        std::path::PathBuf::from(home).join(".hui-agent/uploads")
    } else {
        std::path::PathBuf::from(workspace.trim()).join(".hui-agent/uploads")
    };
    std::fs::create_dir_all(&base).map_err(|e| e.to_string())?;
    Ok(base)
}

fn is_image_ext(ext: &str) -> bool {
    matches!(
        ext.to_ascii_lowercase().as_str(),
        "png" | "jpg" | "jpeg" | "webp" | "gif" | "bmp" | "heic" | "heif"
    )
}

#[derive(serde::Serialize)]
pub struct ImportedImageInfo {
    pub path: String,
    pub name: String,
}

#[tauri::command]
pub fn import_companion_image(source_path: String) -> Result<ImportedImageInfo, String> {
    let source = std::path::Path::new(source_path.trim());
    if !source.is_file() {
        return Err("file not found".into());
    }
    let ext = source
        .extension()
        .and_then(|e| e.to_str())
        .ok_or_else(|| "unsupported image type".to_string())?;
    if !is_image_ext(ext) {
        return Err("unsupported image type".into());
    }

    let dest_dir = uploads_dir()?;
    let file_name = format!("{}.{ext}", uuid_simple());
    let dest = dest_dir.join(&file_name);
    std::fs::copy(source, &dest).map_err(|e| e.to_string())?;

    let name = source
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(&file_name)
        .to_string();

    Ok(ImportedImageInfo {
        path: dest.to_string_lossy().into_owned(),
        name,
    })
}

#[derive(serde::Serialize)]
pub struct WorkspaceMentionFile {
    pub path: String,
    pub rel: String,
}

const SKIP_DIR_NAMES: &[&str] = &[
    ".git",
    "node_modules",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".hui-agent",
    ".cursor",
];

const MENTION_EXTENSIONS: &[&str] = &[
    "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "rs", "go", "java", "kt", "swift", "c", "cpp",
    "h", "hpp", "css", "scss", "html", "md", "json", "yaml", "yml", "toml", "sql", "sh", "txt",
    "vue", "svelte", "webp", "png", "jpg", "jpeg", "gif",
];

fn mention_file_allowed(path: &std::path::Path) -> bool {
    if !path.is_file() {
        return false;
    }
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| MENTION_EXTENSIONS.iter().any(|ext| ext.eq_ignore_ascii_case(e)))
        .unwrap_or(false)
}

fn mention_dir_skipped(name: &str) -> bool {
    SKIP_DIR_NAMES.iter().any(|skip| skip.eq_ignore_ascii_case(name))
}

fn collect_workspace_mention_files(
    root: &std::path::Path,
    dir: &std::path::Path,
    query: &str,
    out: &mut Vec<WorkspaceMentionFile>,
    limit: usize,
    depth: usize,
) {
    if out.len() >= limit || depth > 8 {
        return;
    }
    let entries = match std::fs::read_dir(dir) {
        Ok(v) => v,
        Err(_) => return,
    };
    let mut names: Vec<_> = entries.filter_map(|e| e.ok()).collect();
    names.sort_by_key(|e| e.file_name());
    for entry in names {
        if out.len() >= limit {
            break;
        }
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_dir() {
            if mention_dir_skipped(&name) {
                continue;
            }
            collect_workspace_mention_files(root, &path, query, out, limit, depth + 1);
            continue;
        }
        if !mention_file_allowed(&path) {
            continue;
        }
        let rel = path
            .strip_prefix(root)
            .unwrap_or(&path)
            .to_string_lossy()
            .replace('\\', "/");
        if !query.is_empty() {
            let q = query.to_ascii_lowercase();
            let rel_l = rel.to_ascii_lowercase();
            let name_l = name.to_ascii_lowercase();
            if !rel_l.contains(&q) && !name_l.contains(&q) {
                continue;
            }
        }
        out.push(WorkspaceMentionFile {
            path: path.to_string_lossy().into_owned(),
            rel,
        });
    }
}

#[tauri::command]
pub fn list_workspace_mention_files(
    query: String,
    limit: Option<usize>,
) -> Result<Vec<WorkspaceMentionFile>, String> {
    let workspace = read_cursor_workspace();
    if workspace.trim().is_empty() {
        return Ok(vec![]);
    }
    let root = std::path::PathBuf::from(workspace.trim());
    if !root.is_dir() {
        return Err("workspace not found".into());
    }
    let max = limit.unwrap_or(20).clamp(1, 50);
    let mut out = Vec::new();
    collect_workspace_mention_files(&root, &root, query.trim(), &mut out, max, 0);
    Ok(out)
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
    let workspace = read_cursor_workspace();
    let mut env = serde_json::Map::new();
    env.insert(
        "TTS_PROXY_PORT".into(),
        serde_json::Value::String(std::env::var("TTS_PROXY_PORT").unwrap_or_else(|_| "8896".into())),
    );
    env.insert(
        "EDGE_TTS_VOICE".into(),
        serde_json::Value::String(
            std::env::var("EDGE_TTS_VOICE").unwrap_or_else(|_| "zh-CN-XiaoxiaoNeural".into()),
        ),
    );
    if !workspace.is_empty() {
        env.insert("HUI_AGENT_WORKSPACE".into(), serde_json::Value::String(workspace));
    }
    let cfg = serde_json::json!({
        "mcpServers": {
            "hui-agent-desktop": {
                "command": python,
                "args": ["-m", "hui_mcp"],
                "env": env
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
    image_paths: Option<Vec<String>>,
    file_paths: Option<Vec<String>>,
    services: State<'_, Arc<ServiceManager>>,
    app: AppHandle,
) -> Result<CompanionChatResult, String> {
    let _ = services;
    app.emit("companion-task", &text).ok();
    let mut body = serde_json::json!({ "text": text });
    if let Some(paths) = image_paths {
        let cleaned: Vec<String> = paths
            .into_iter()
            .map(|p| p.trim().to_string())
            .filter(|p| !p.is_empty())
            .collect();
        if !cleaned.is_empty() {
            body["image_paths"] = serde_json::Value::Array(
                cleaned.into_iter().map(serde_json::Value::String).collect(),
            );
        }
    }
    if let Some(paths) = file_paths {
        let cleaned: Vec<String> = paths
            .into_iter()
            .map(|p| p.trim().to_string())
            .filter(|p| !p.is_empty())
            .collect();
        if !cleaned.is_empty() {
            body["file_paths"] = serde_json::Value::Array(
                cleaned.into_iter().map(serde_json::Value::String).collect(),
            );
        }
    }
    let v = daemon_post("/agent/chat", body).await?;
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

fn ensure_draw_overlay(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(w) = app.get_webview_window("draw-overlay") {
        let _ = w.set_always_on_top(false);
        return Ok(w);
    }
    let mut builder = WebviewWindowBuilder::new(
        app,
        "draw-overlay",
        WebviewUrl::App("index.html".into()),
    )
    .title("")
    .decorations(false)
    .transparent(true)
    .always_on_top(false)
    .skip_taskbar(true)
    .visible(false)
    .resizable(false)
    .focused(false)
    .accept_first_mouse(true);

    #[cfg(target_os = "macos")]
    {
        builder = builder.visible_on_all_workspaces(true);
    }

    let win = builder.build().map_err(|e| e.to_string())?;

    #[cfg(target_os = "macos")]
    {
        use tauri::window::Color;
        let _ = win.set_background_color(Some(Color(0, 0, 0, 0)));
    }

    Ok(win)
}

fn position_draw_overlay(app: &AppHandle, win: &WebviewWindow) -> Result<(), String> {
    let companion = app
        .get_webview_window("companion")
        .ok_or_else(|| "companion window missing".to_string())?;
    let monitor = companion
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "monitor not found".to_string())?;
    let scale = monitor.scale_factor();
    let area = monitor.work_area();
    let x = area.position.x as f64 / scale;
    let y = area.position.y as f64 / scale;
    let w = area.size.width as f64 / scale;
    let h = area.size.height as f64 / scale;
    win.set_size(LogicalSize::new(w, h))
        .map_err(|e| e.to_string())?;
    win.set_position(LogicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn raise_companion_window(app: &AppHandle) -> Result<(), String> {
    let companion = app
        .get_webview_window("companion")
        .ok_or_else(|| "companion window missing".to_string())?;
    companion
        .set_always_on_top(true)
        .map_err(|e| e.to_string())?;
    companion.show().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn companion_raise(app: AppHandle) -> Result<(), String> {
    raise_companion_window(&app)
}

#[tauri::command]
pub fn companion_draw_show(app: AppHandle) -> Result<(), String> {
    let win = ensure_draw_overlay(&app)?;
    position_draw_overlay(&app, &win)?;
    win.set_ignore_cursor_events(false)
        .map_err(|e| e.to_string())?;
    win.show().map_err(|e| e.to_string())?;
    raise_companion_window(&app)?;
    win.set_focus().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn companion_draw_hide(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("draw-overlay") {
        win.hide().map_err(|e| e.to_string())?;
    }
    raise_companion_window(&app)?;
    let _ = app.emit_to("companion", "companion-draw-exited", ());
    Ok(())
}

#[tauri::command]
pub fn companion_draw_clear(app: AppHandle) -> Result<(), String> {
    let _ = app.emit_to("draw-overlay", "companion-draw-clear", ());
    Ok(())
}
