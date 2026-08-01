"""macOS user notifications for Companion / doc-read flows."""

from __future__ import annotations

import platform
import subprocess


def macos_notify(title: str, subtitle: str = "", body: str = "") -> None:
    if platform.system() != "Darwin":
        return
    safe_title = title.replace('"', "'")[:120]
    safe_sub = subtitle.replace('"', "'")[:120]
    safe_body = body.replace('"', "'")[:200]
    script = (
        f'display notification "{safe_body}" '
        f'with title "{safe_title}" subtitle "{safe_sub}"'
    )
    subprocess.run(["osascript", "-e", script], check=False)
