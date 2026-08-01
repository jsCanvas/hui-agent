"""Bring the user's document app to the foreground (not HuiAgent)."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

_SKIP_APPS = frozenset(
    {
        "HuiAgent",
        "hui-agent-desktop",
        "Electron",
        "Cursor",
        "System Settings",
        "System Preferences",
        "loginwindow",
        "WindowManager",
        "Control Center",
        "Notification Center",
    }
)

_DOC_APPS = (
    "Google Chrome",
    "Safari",
    "Arc",
    "Microsoft Edge",
    "Firefox",
    "Chromium",
    "Feishu",
    "Lark",
    "LarkSuite",
    "飞书",
)

_LAST_DOC_APP = Path.home() / ".hui-agent" / "last-doc-app.txt"

_ACTIVATE_SCRIPT = """
tell application "System Events"
    set skipList to {SKIP_LIST}
    set browserList to {BROWSER_LIST}
    set preferred to "{PREFERRED}"
    set lastApp to "{LAST}"
    if preferred is not "" then
        try
            tell application preferred to activate
        end try
        repeat with p in (application processes whose visible is true)
            if name of p is preferred then
                set frontmost of p to true
                return preferred
            end if
        end repeat
    end if
    if lastApp is not "" then
        try
            tell application lastApp to activate
        end try
        repeat with p in (application processes whose visible is true)
            if name of p is lastApp then
                set frontmost of p to true
                return lastApp
            end if
        end repeat
    end if
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
        if skipList does not contain n then
            set frontmost of p to true
            return n
        end if
    end repeat
end tell
return ""
""".strip()


def _preferred_doc_app() -> str | None:
    cfg_path = Path.home() / ".hui-agent" / "config.json"
    if not cfg_path.is_file():
        return None
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        app = (raw.get("doc_read") or {}).get("preferred_app") or ""
        app = str(app).strip()
        return app or None
    except (json.JSONDecodeError, OSError):
        return None


def _last_doc_app() -> str | None:
    if not _LAST_DOC_APP.is_file():
        return None
    try:
        name = _LAST_DOC_APP.read_text(encoding="utf-8").strip()
        return name or None
    except OSError:
        return None


def _remember_doc_app(name: str | None) -> None:
    if not name:
        return
    try:
        _LAST_DOC_APP.parent.mkdir(parents=True, exist_ok=True)
        _LAST_DOC_APP.write_text(name, encoding="utf-8")
    except OSError:
        pass


def activate_document_app(*, skip: frozenset[str] | None = None) -> str | None:
    """Activate a visible non-agent app. Returns app name or None."""
    if platform.system() != "Darwin":
        return None
    skip_all = _SKIP_APPS | (skip or frozenset())
    skip_literal = "{" + ", ".join(f'"{s}"' for s in sorted(skip_all)) + "}"
    browser_literal = "{" + ", ".join(f'"{b}"' for b in _DOC_APPS) + "}"
    preferred = (_preferred_doc_app() or "").replace('"', '\\"')
    last_app = (_last_doc_app() or "").replace('"', '\\"')
    script = (
        _ACTIVATE_SCRIPT.replace("{SKIP_LIST}", skip_literal)
        .replace("{BROWSER_LIST}", browser_literal)
        .replace("{PREFERRED}", preferred)
        .replace("{LAST}", last_app)
    )
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        name = out.stdout.strip()
        if name:
            _remember_doc_app(name)
        return name or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def activate_browser_for_reading() -> str | None:
    """Bring browser/document to foreground; never activate Cursor or Companion."""
    return activate_document_app()


def activate_cursor_app() -> str | None:
    """Bring Cursor IDE to the foreground."""
    if platform.system() != "Darwin":
        return None
    script = """
tell application "Cursor" to activate
tell application "System Events"
    repeat with p in (application processes whose visible is true)
        if name of p is "Cursor" then
            set frontmost of p to true
            return "Cursor"
        end if
    end repeat
end tell
return ""
""".strip()
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        name = out.stdout.strip()
        return name or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
