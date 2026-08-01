#!/usr/bin/env bash
# Best-effort: paste Companion follow-up into Cursor Agent chat.
# Usage: trigger-cursor-companion-task.sh [--background|--notify-only]
#   --background     auto-submit via Cmd+I, then restore previous front app (doc stays visible)
#   --notify-only    copy follow-up to clipboard only; never activate Cursor
set -euo pipefail

BACKGROUND=0
NOTIFY_ONLY=0
for arg in "${@:-}"; do
  case "$arg" in
    --background) BACKGROUND=1 ;;
    --notify-only) NOTIFY_ONLY=1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MCP="$ROOT/mcp-server"
PY="$MCP/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  PY=python3
fi

json=""
if [[ -n "${HUI_TASK_ID:-}" && -n "${HUI_TASK_TEXT:-}" ]]; then
  json="$(
    cd "$MCP" && "$PY" -m hui_mcp.companion_followup \
      --task-id "$HUI_TASK_ID" --text "$HUI_TASK_TEXT" 2>/dev/null || true
  )"
fi
if [[ -z "$json" ]]; then
  json="$(
    cd "$MCP" && "$PY" -m hui_mcp.companion_followup 2>/dev/null || true
  )"
fi
if [[ -z "$json" ]]; then
  exit 0
fi

msg="$(
  printf '%s' "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('followup_message',''))" 2>/dev/null || true
)"
if [[ -z "$msg" ]]; then
  exit 0
fi

printf '%s' "$msg" | pbcopy

if [[ "$NOTIFY_ONLY" == "1" ]]; then
  osascript -e 'display notification "Cursor 指令已复制到剪贴板（未切换窗口）" with title "Companion" subtitle "可在方便时粘贴到 Agent"' || true
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  exit 0
fi

if [[ "$BACKGROUND" == "1" ]]; then
  osascript <<'APPLESCRIPT' || true
on browserFront()
  set browserList to {"Google Chrome", "Safari", "Arc", "Microsoft Edge", "Firefox", "Chromium", "Feishu", "Lark", "LarkSuite", "飞书"}
  tell application "System Events"
    repeat with b in browserList
      repeat with p in (application processes whose visible is true)
        if name of p is b then
          set frontmost of p to true
          return b
        end if
      end repeat
    end repeat
    repeat with p in (application processes whose visible is true)
      set n to name of p
      if n is not "Cursor" and n is not "HuiAgent" and n is not "hui-agent-desktop" and n is not "Electron" then
        set frontmost of p to true
        return n
      end if
    end repeat
  end tell
  return ""
end browserFront

tell application "System Events"
  set prevApp to name of first application process whose frontmost is true
end tell

tell application "Cursor" to activate
delay 0.45
tell application "System Events"
  tell process "Cursor"
    set frontmost to true
    keystroke "i" using {command down}
    delay 0.85
    keystroke "v" using command down
    delay 0.25
    keystroke return
  end tell
end tell

delay 0.35
set restored to browserFront()
if restored is "" then
  tell application "System Events"
    repeat with p in (application processes whose visible is true)
      if name of p is prevApp then
        set frontmost of p to true
        exit repeat
      end if
    end repeat
  end tell
end if
APPLESCRIPT
  osascript -e 'display notification "Cursor 已在后台开始处理；已切回文档页" with title "Companion 文档任务" subtitle "Agent 已自动启动"' || true
  exit 0
fi

osascript <<'APPLESCRIPT' || true
tell application "Cursor" to activate
delay 0.5
tell application "System Events"
  tell process "Cursor"
    set frontmost to true
    keystroke "i" using {command down}
    delay 0.8
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
APPLESCRIPT
