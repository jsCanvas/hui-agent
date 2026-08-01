mod companion_socket;
mod process;
mod tray;

use std::sync::Arc;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let services = Arc::new(
        process::ServiceManager::new().expect("failed to init ServiceManager"),
    );

    let socket_tx = Arc::new(std::sync::Mutex::new(None));
    let socket_state = companion_socket::SocketState {
        tx: socket_tx.clone(),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(services.clone())
        .manage(socket_state)
        .setup(move |app| {
            if let Err(e) = services.start_all() {
                eprintln!("[hui-agent] service start warning: {e}");
            }
            services.clone().start_watchdog();
            companion_socket::start_companion_socket(app.handle().clone(), socket_tx);
            tray::setup_tray(app.handle())?;
            if let Some(companion) = app.get_webview_window("companion") {
                #[cfg(target_os = "macos")]
                {
                    use tauri::window::Color;
                    let _ = companion.set_background_color(Some(Color(0, 0, 0, 0)));
                }
                let _ = companion.show();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "companion" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            tray::get_service_status,
            tray::restart_services,
            tray::export_cursor_config,
            tray::export_socket_info,
            tray::app_exit,
            tray::companion_reset_position,
            tray::companion_send_message,
            tray::companion_relay_status,
            tray::tts_speak,
            tray::tts_stop,
            tray::voice_call_start,
            tray::voice_call_stop,
            tray::voice_process_utterance,
            tray::companion_stt_start,
            tray::companion_stt_stop,
            tray::companion_stt_poll,
            companion_socket::companion_voice_stt,
            companion_socket::companion_voice_speak_done,
            companion_socket::companion_automation_consent_response,
            companion_socket::companion_socket_status,
        ])
        .build(tauri::generate_context!())
        .expect("error building tauri app")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(svc) = app_handle.try_state::<Arc<process::ServiceManager>>() {
                    svc.stop_all();
                }
            }
        });
}
