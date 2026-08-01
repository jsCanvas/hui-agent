# HuiAgent: Desktop AI Companion and Cursor MCP Co-Architecture

> **Technical Paper v1.0** · 2026-08-01  
> **Authors**: HuiAgent Team / jsCanvas  
> **Repository**: [https://github.com/jsCanvas/hui-agent](https://github.com/jsCanvas/hui-agent)  
> **Project site**: [https://jscanvas.github.io/hui-agent/](https://jscanvas.github.io/hui-agent/) (GitHub Pages)  
> **中文版本**: [PAPER.md](./PAPER.md)

---

## Abstract

HuiAgent is a **local desktop AI companion** system for knowledge workers. It couples a transparent overlay UI (Companion), a Python Daemon, a Model Context Protocol (MCP) tool chain, and the Cursor IDE Agent over a long-lived Socket connection, closing the loop of **observe screen → understand documents → operate keyboard and mouse → respond in spoken Chinese**. The Companion input area supports **workspace selection, image upload, `@` references to project files, and on-screen brush annotation**; tasks can carry file and image context for Cursor **vibe coding**. This paper describes its layered architecture, duplex voice edge responses, the Cursor Socket Relay task model, and an active reading workflow that uses screen capture and scrolling instead of background OCR. The system has been validated on macOS for scenarios such as voice-driven Feishu document reading and Companion push-to-talk calls.

**Keywords**: desktop automation, MCP, Cursor Agent, duplex voice, screen understanding, local daemon

---

## 1. Introduction

Large-model agents already assist coding efficiently inside IDEs, yet much of a user's work happens in browsers, documents, and collaboration tools. Cloud agents cannot directly access the local screen and input devices; traditional RPA lacks semantic understanding and conversational interaction. HuiAgent is positioned as the **local agent of the hui-agent platform**: it exposes standard MCP interfaces on the desktop, provides a minimally intrusive Companion overlay, and integrates with MCP hosts such as Cursor so that **the AI brain lives in the IDE while eyes and hands live in the OS** becomes a deployable architecture.

**Contributions**:

1. **Companion + Daemon + MCP** separation: Companion is only the entry point and TTS/STT surface; complex reasoning is delegated to Cursor.
2. **Socket Relay (`:18765`)** lets Companion tasks block on an NDJSON long connection until Cursor completes work, reducing frequent foreground switching.
3. **Duplex voice**: a local edge layer gives instant acknowledgements and simple tool execution; Cursor asynchronously takes over full planning.
4. **Active screen-reading workflow**: `get_screenshot` + visual understanding + small-step `mouse_scroll`, replacing the default background OCR worker.
5. **Companion task input enhancements**: workspace binding, `@` mentions of files/images, on-screen brush annotation; task text automatically appends `[workspace file]` / `[uploaded image]` context.

---

## 2. Related Work

| Area | Representative approaches | Difference from HuiAgent |
|------|---------------------------|--------------------------|
| IDE Agent | Cursor, Copilot | Focus on codebases; weak desktop UI integration |
| MCP | Anthropic MCP specification | HuiAgent provides a desktop host-side implementation |
| RPA | UiPath, AutoHotkey | Rule-driven; no unified LLM tool protocol |
| Voice assistant | Siri, smart speakers | No document screen reading or IDE co-operation |

HuiAgent fills the gap between **MCP desktop tool host + lightweight Companion UI + Cursor as the brain**.

---

## 3. System Architecture

```
┌──────────────────┐   WebSocket/NDJSON    ┌─────────────────────┐
│ Companion (Tauri)│ ◄──────────────────► │ Daemon (Python)      │
│ React · VRM/TTS  │                       │ Capture · TTS · STT  │
└────────┬─────────┘                       │ Socket Bridge :18765 │
         │                                   └──────────┬──────────┘
         │ invoke                                      │
         ▼                                               │ role=cursor
┌──────────────────┐         MCP stdio         ┌─────────▼──────────┐
│ Settings · Tray  │                           │ cursor-socket-client│
└──────────────────┘                           └─────────┬──────────┘
                                                           │
                                              ┌────────────▼────────────┐
                                              │ Cursor Agent + MCP      │
                                              │ 22+ tools: screenshot,  │
                                              │ mouse_*, keyboard_*,    │
                                              │ companion_speak, …      │
                                              └─────────────────────────┘
```

### 3.1 Companion Overlay

- Transparent bottom-right window: avatar portrait, PTT/text input, status overlay (listening / executing).
- No long chat log; progress is conveyed through status and TTS feedback.
- Tauri 2 shell manages child processes, system tray, and Socket event forwarding.

### 3.2 Companion Task Input and Screen Annotation

A **workspace and attachment toolbar** sits above the input field:

| Capability | Description |
|------------|-------------|
| **Select workspace** | Bind the Cursor project directory; persisted in `cursor.workspace` inside `~/.hui-agent/config.json` |
| **Upload images** | Multi-select import to `{workspace}/.hui-agent/uploads/`; badge count on the icon; hover to preview and remove |
| **`@` mentions** | Type `@` to pick workspace files and uploaded images; inserts `@path` / `@filename` into the prompt |
| **Brush / eraser** | Full-screen transparent overlay for on-page line annotation; eraser clears strokes; `Esc` or toggling brush exits |
| **Window stacking** | Companion stays `alwaysOnTop`, floating above the draw overlay |

On send, Rust → Daemon → `runtime._compose_task_text` resolves `@` references, merges `file_paths` and `image_paths`, and appends:

```
[工作区文件: /abs/path/to/file.ts]
[用户上传图片: /abs/path/to/photo.png]

请结合以上 @ 引用的工作区文件与图片，在当前项目上下文中分析并协助 vibe coding。
```

Workspace file suggestions come from the Tauri command `list_workspace_mention_files`, which walks the local tree while skipping `.git`, `node_modules`, and similar directories.

### 3.3 Daemon and Socket Bridge

- **Health**: `http://127.0.0.1:18766/health`
- **Frame buffer**: 10 fps ring buffer for `get_recent_frames`
- **Relay**: `cursor_relay.py` maintains pending tasks and waits for `companion_task_complete`
- **Voice**: `/voice/*` HTTP plus Socket event `voice.stt.final`

### 3.4 MCP Tool Set

Core tools include: `get_screenshot`, `get_screen_info`, `mouse_move`, `mouse_click`, `mouse_scroll`, `keyboard_*`, `activate_document_app`, `companion_speak`, `companion_task_pending`, `companion_task_complete`, `companion_socket_connect_and_wait`, and others.

Automation can be gated by `automation.require_consent`; in development mode the Companion confirmation dialog can be disabled.

---

## 4. Cursor Socket Relay Task Model

### 4.1 Connection and Listening

1. The agent calls `companion_socket_connect_and_wait` (or runs `connect-cursor-socket.sh`).
2. Background process `cursor-socket-client.py` connects to the Bridge with `role=cursor`, listening for up to 12 hours by default.
3. `wait_for_task` polls Daemon pending tasks; Companion shows “listening”.

### 4.2 Task Loop

```
wait → task_received → companion_task_pending
     → [screen read / keyboard & mouse / speak]
     → companion_task_complete (auto_wait=true)
     → automatic companion_socket_wait → next task
```

With `auto_wait`, the same MCP call enters the next listen cycle after task submission, reducing missed `wait` invocations by the agent.

### 4.3 UI Policy

- **Do not** use `activate_cursor_app` / `cmd+tab` to bring Cursor to the foreground (Relay mode).
- Document focus: `mouse_move` + `mouse_click` on the document area (roughly 32% width, 42% height).
- Scrolling: `|dy| ≤ 24`; avoid repeated Page Down.

---

## 5. Duplex Voice

After user PTT input is converted to text by STT:

| Layer | Latency | Behavior |
|-------|---------|----------|
| **Edge (builtin/GGUF)** | ~100 ms | Instant ack TTS; optional simple actions such as `get_screenshot` |
| **Cursor** | seconds to minutes | Full planning, multi-screen reading, segmented `companion_speak` |

`voice_pending.duplex` carries `ack_text`, `executed_actions`, and `defer_to_cursor: true`; Cursor follow-ups should not repeat the ack.

---

## 6. Document Reading Workflow (Case Study)

**Scenario**: Feishu Wiki English novel; user says “read this novel in Chinese”.

1. Edge ack and first screenshot.
2. Cursor uses small-step `mouse_scroll`, repeated `get_screenshot` to locate synopsis and body boundaries.
3. `companion_speak` delivers a segmented Chinese spoken summary.
4. `companion_task_complete` submits a Markdown summary and `auto_wait` resumes listening.

This flow does not rely on `companion_doc_read_start` background OCR, reducing inconsistency with foreground document state.

---

## 7. Implementation and Deployment

- **Client path**: `repo/client/` (Tauri + React + Python MCP)
- **Dependencies**: Rust, Node 20+, Python 3.12; macOS requires Screen Recording and Accessibility permissions
- **Configuration**: `~/.hui-agent/config.json` (TTS/STT/agent/automation/doc_read)
- **Start**: `npm run dev`

See the [site guide](https://jscanvas.github.io/hui-agent/#guide) and [Companion usage](../docs/prd/companion-usage.md) for installation and permissions.

---

## 8. Discussion and Limitations

| Topic | Notes |
|-------|-------|
| Platform | macOS first; Windows Tauri builds exist; input layer needs more testing |
| MCP blocking | Long `auto_wait` listens may hit MCP HTTP timeouts; use `timeout_sec` or `auto_wait: false` |
| Draw overlay | Annotation layer uses normal window level; Companion stays on top; may be obscured by full-screen apps |
| Privacy | Screenshots and input stay on device; Relay does not upload the screen to a hui-agent cloud |
| Models | Default Cursor cloud models; optional local GGUF only for edge outline/ack |

---

## 9. Conclusion

HuiAgent demonstrates how **MCP desktop tools**, a **lightweight Companion UI**, and the **Cursor Agent** can be combined into a reproducible desktop AI workflow. Socket Relay and Duplex design keep the IDE as the brain while providing a voice entry point and long-running listen capability. We open-source the full client and publish demo animations and step-by-step guidance on the project site for community extension and integration.

---

## References and Links

1. Anthropic. *Model Context Protocol*. [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
2. Cursor. *Cursor IDE Documentation*. [https://cursor.com/docs](https://cursor.com/docs)
3. **HuiAgent source**: [https://github.com/jsCanvas/hui-agent](https://github.com/jsCanvas/hui-agent)
4. **HuiAgent site**: [https://jscanvas.github.io/hui-agent/](https://jscanvas.github.io/hui-agent/)
5. In-repo docs: `docs/prd/desktop-mcp-client.md`, `docs/solution/desktop-mcp-client.md`

---

## Appendix A: Quick Commands

```bash
git clone https://github.com/jsCanvas/hui-agent.git
cd hui-agent/repo/client && npm run dev
./scripts/connect-cursor-socket.sh
curl -sf http://127.0.0.1:18766/health | python3 -m json.tool
```

## Appendix B: Version Information

| Component | Version |
|-----------|---------|
| MCP Server | 0.1.8 |
| Companion input enhancements | v0.2 (workspace · @ mentions · images · brush) |
| Paper | v1.1 |
| Date | 2026-08-01 |
