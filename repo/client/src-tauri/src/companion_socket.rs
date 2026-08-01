use std::io::{BufRead, BufReader, ErrorKind, Write};
use std::net::TcpStream;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use tauri::{AppHandle, Emitter};

pub struct SocketState {
    pub tx: Arc<Mutex<Option<mpsc::Sender<String>>>>,
}

fn read_socket_config() -> Result<(String, u16, String), String> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map_err(|_| "HOME not set".to_string())?;
    let path = format!("{home}/.hui-agent/config.json");
    let text = std::fs::read_to_string(&path).map_err(|e| format!("read config: {e}"))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("parse config: {e}"))?;
    let sock = &v["socket"];
    let host = sock["host"].as_str().unwrap_or("127.0.0.1").to_string();
    let port = sock["port"].as_u64().unwrap_or(18765) as u16;
    let token = sock["token"].as_str().unwrap_or("").to_string();
    if token.is_empty() {
        return Err("missing socket.token in config".into());
    }
    Ok((host, port, token))
}

fn send_line(stream: &mut TcpStream, obj: &serde_json::Value) -> Result<(), String> {
    let line = serde_json::to_string(obj).map_err(|e| e.to_string())? + "\n";
    stream
        .write_all(line.as_bytes())
        .map_err(|e| format!("socket write: {e}"))?;
    stream.flush().map_err(|e| format!("socket flush: {e}"))
}

fn recv_line(reader: &mut BufReader<TcpStream>) -> Result<serde_json::Value, String> {
    loop {
        let mut buf = String::new();
        match reader.read_line(&mut buf) {
            Ok(0) => return Err("socket closed".into()),
            Ok(_) => {
                if buf.trim().is_empty() {
                    continue;
                }
                return serde_json::from_str(buf.trim()).map_err(|e| format!("json parse: {e}"));
            }
            Err(e)
                if matches!(
                    e.kind(),
                    ErrorKind::WouldBlock | ErrorKind::TimedOut | ErrorKind::Interrupted
                ) =>
            {
                continue;
            }
            Err(e) => return Err(format!("socket read: {e}")),
        }
    }
}

fn handle_inbound(app: &AppHandle, msg: &serde_json::Value) {
    let mtype = msg.get("type").and_then(|v| v.as_str()).unwrap_or("");
    match mtype {
        "voice.speak" => {
            let _ = app.emit(
                "companion-voice-speak",
                serde_json::json!({
                    "text": msg.get("text").and_then(|v| v.as_str()).unwrap_or(""),
                    "final": msg.get("final").and_then(|v| v.as_bool()).unwrap_or(false),
                    "interrupt": msg.get("interrupt").and_then(|v| v.as_bool()).unwrap_or(false),
                    "utterance_id": msg.get("utterance_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "speak_id": msg.get("speak_id").and_then(|v| v.as_str()).unwrap_or(""),
                }),
            );
        }
        "voice.turn.done" => {
            let _ = app.emit(
                "companion-voice-turn-done",
                serde_json::json!({
                    "utterance_id": msg.get("utterance_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "ok": msg.get("ok").and_then(|v| v.as_bool()).unwrap_or(false),
                    "reply": msg.get("reply").and_then(|v| v.as_str()).unwrap_or(""),
                }),
            );
        }
        "voice.utterance.accepted" => {
            let _ = app.emit(
                "companion-voice-utterance-accepted",
                serde_json::json!({
                    "utterance_id": msg.get("utterance_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "ok": msg.get("ok").and_then(|v| v.as_bool()).unwrap_or(false),
                    "error": msg.get("error").and_then(|v| v.as_str()).unwrap_or(""),
                }),
            );
        }
        "agent.task.started" => {
            let _ = app.emit(
                "companion-agent-started",
                serde_json::json!({
                    "task_id": msg.get("task_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "text": msg.get("text").and_then(|v| v.as_str()).unwrap_or(""),
                    "channel": msg.get("channel").and_then(|v| v.as_str()).unwrap_or("text"),
                }),
            );
        }
        "automation.consent.request" => {
            let _ = app.emit(
                "companion-automation-consent",
                serde_json::json!({
                    "request_id": msg.get("request_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "scope": msg.get("scope").and_then(|v| v.as_str()).unwrap_or(""),
                    "tool": msg.get("tool").and_then(|v| v.as_str()).unwrap_or(""),
                    "message": msg.get("message").and_then(|v| v.as_str()).unwrap_or(""),
                }),
            );
        }
        "agent.wait.state" => {
            let _ = app.emit(
                "companion-agent-wait",
                serde_json::json!({
                    "waiting": msg.get("waiting").and_then(|v| v.as_bool()).unwrap_or(false),
                    "remaining_sec": msg.get("remaining_sec"),
                }),
            );
        }
        "error" => {
            eprintln!(
                "[companion-socket] error {}: {}",
                msg.get("code").and_then(|v| v.as_str()).unwrap_or(""),
                msg.get("message").and_then(|v| v.as_str()).unwrap_or("")
            );
        }
        _ => {}
    }
}

fn connect_once(
    app: AppHandle,
    out_slot: Arc<Mutex<Option<mpsc::Sender<String>>>>,
    host: &str,
    port: u16,
    token: &str,
) -> Result<(), String> {
    let mut stream = TcpStream::connect((host, port)).map_err(|e| format!("connect: {e}"))?;
    // Blocking read — companion socket may sit idle for long periods waiting for voice events.
    stream.set_read_timeout(None).ok();
    stream.set_write_timeout(None).ok();
    let mut reader = BufReader::new(stream.try_clone().map_err(|e| e.to_string())?);

    send_line(&mut stream, &serde_json::json!({"type": "auth", "token": token}))?;
    let auth = recv_line(&mut reader)?;
    if auth.get("type").and_then(|v| v.as_str()) != Some("auth.ok") {
        return Err(format!("auth failed: {auth}"));
    }

    send_line(
        &mut stream,
        &serde_json::json!({"type": "agent.register", "role": "companion"}),
    )?;
    let reg = recv_line(&mut reader)?;
    if reg.get("type").and_then(|v| v.as_str()) != Some("agent.registered") {
        return Err(format!("register failed: {reg}"));
    }

    eprintln!("[companion-socket] connected {host}:{port}");

    let (out_tx, out_rx) = mpsc::channel::<String>();
    *out_slot.lock().unwrap() = Some(out_tx);

    let read_app = app.clone();
    let read_handle = thread::spawn(move || {
        loop {
            match recv_line(&mut reader) {
                Ok(msg) => handle_inbound(&read_app, &msg),
                Err(e) => {
                    eprintln!("[companion-socket] read error: {e}");
                    break;
                }
            }
        }
    });

    for line in out_rx {
        if stream.write_all(line.as_bytes()).is_err() {
            break;
        }
        let _ = stream.flush();
    }

    let _ = read_handle.join();
    *out_slot.lock().unwrap() = None;
    Err("connection closed".into())
}

pub fn start_companion_socket(app: AppHandle, out_slot: Arc<Mutex<Option<mpsc::Sender<String>>>>) {
    thread::spawn(move || {
        let mut backoff = 1.0f64;
        loop {
            let cfg = match read_socket_config() {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("[companion-socket] config error: {e}; retry in {backoff}s");
                    thread::sleep(Duration::from_secs(backoff as u64));
                    backoff = (backoff * 2.0).min(30.0);
                    continue;
                }
            };
            let (host, port, token) = cfg;
            match connect_once(app.clone(), out_slot.clone(), &host, port, &token) {
                Ok(()) => {}
                Err(e) => eprintln!("[companion-socket] {e}; reconnect in {backoff}s"),
            }
            thread::sleep(Duration::from_secs(backoff as u64));
            backoff = (backoff * 2.0).min(30.0);
        }
    });
}

fn send_json(state: &SocketState, obj: &serde_json::Value) -> Result<(), String> {
    let line = serde_json::to_string(obj).map_err(|e| e.to_string())? + "\n";
    let guard = state.tx.lock().map_err(|e| e.to_string())?;
    let tx = guard
        .as_ref()
        .ok_or_else(|| "companion socket offline".to_string())?;
    tx.send(line).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn companion_voice_stt(
    partial: bool,
    text: String,
    state: tauri::State<'_, SocketState>,
) -> Result<serde_json::Value, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("empty text".into());
    }
    let mtype = if partial {
        "voice.stt.partial"
    } else {
        "voice.stt.final"
    };
    send_json(
        state.inner(),
        &serde_json::json!({
            "type": mtype,
            "text": trimmed,
            "confidence": 0.9
        }),
    )?;
    Ok(serde_json::json!({"ok": true, "partial": partial}))
}

#[tauri::command]
pub fn companion_voice_speak_done(
    speak_id: String,
    state: tauri::State<'_, SocketState>,
) -> Result<serde_json::Value, String> {
    let trimmed = speak_id.trim();
    if trimmed.is_empty() {
        return Err("speak_id required".into());
    }
    send_json(
        state.inner(),
        &serde_json::json!({
            "type": "voice.speak.done",
            "speak_id": trimmed,
        }),
    )?;
    Ok(serde_json::json!({"ok": true, "speak_id": trimmed}))
}

#[tauri::command]
pub fn companion_automation_consent_response(
    request_id: String,
    granted: bool,
    state: tauri::State<'_, SocketState>,
) -> Result<serde_json::Value, String> {
    let trimmed = request_id.trim();
    if trimmed.is_empty() {
        return Err("request_id required".into());
    }
    send_json(
        state.inner(),
        &serde_json::json!({
            "type": "automation.consent.response",
            "request_id": trimmed,
            "granted": granted,
        }),
    )?;
    Ok(serde_json::json!({"ok": true, "request_id": trimmed, "granted": granted}))
}

#[tauri::command]
pub fn companion_socket_status(state: tauri::State<'_, SocketState>) -> Result<bool, String> {
    Ok(state.tx.lock().map_err(|e| e.to_string())?.is_some())
}
