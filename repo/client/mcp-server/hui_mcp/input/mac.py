"""macOS input via cliclick + smooth paths."""

from __future__ import annotations

import subprocess
import time

from hui_mcp.input.smooth_path import adaptive_steps, bezier_points, path_distance

# Per-step pause for Bezier segments (cliclick -w); keep low for agent speed.
_MOVE_STEP_WAIT_MS = "1"

_MODIFIERS = frozenset({"cmd", "ctrl", "alt", "option", "shift", "fn"})

_KEY_MAP = {
    "cmd": "cmd",
    "command": "cmd",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "fn": "fn",
    "enter": "return",
    "return": "return",
    "esc": "esc",
    "escape": "esc",
    "tab": "tab",
    "space": "space",
    "delete": "delete",
    "backspace": "delete",
}

# Keys supported by cliclick `kp:` (see cliclick -h error listing)
_KP_KEYS = frozenset(
    {
        "arrow-down",
        "arrow-left",
        "arrow-right",
        "arrow-up",
        "delete",
        "end",
        "enter",
        "esc",
        "escape",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
        "f13",
        "f14",
        "f15",
        "f16",
        "fwd-delete",
        "home",
        "page-down",
        "page-up",
        "return",
        "space",
        "tab",
    }
)


def _normalize_key(key: str) -> str:
    k = key.lower()
    mapped = _KEY_MAP.get(k, k)
    if mapped == "escape":
        return "esc"
    return mapped


def _is_modifier(key: str) -> bool:
    return _normalize_key(key) in _MODIFIERS


def build_hotkey_commands(keys: list[str]) -> list[str]:
    """Build cliclick argv tokens for a keyboard shortcut."""
    mods: list[str] = []
    main_keys: list[str] = []
    for raw in keys:
        norm = _normalize_key(raw)
        if _is_modifier(raw):
            if norm not in mods:
                mods.append(norm)
        else:
            main_keys.append(norm)

    if len(main_keys) != 1:
        raise ValueError(f"hotkey expects one non-modifier key, got {main_keys!r}")

    main = main_keys[0]
    cmds: list[str] = ["w:40"]
    if mods:
        cmds.append(f"kd:{','.join(mods)}")
    if main in _KP_KEYS:
        cmds.append(f"kp:{main}")
    elif len(main) == 1:
        cmds.append(f"t:{main}")
    else:
        raise ValueError(f"unsupported hotkey key: {main}")

    if mods:
        cmds.append(f"ku:{','.join(mods)}")
    return cmds


class MacInputDriver:
    def _run_cliclick(self, *cmds: str) -> None:
        subprocess.run(["cliclick", "-w", _MOVE_STEP_WAIT_MS, *cmds], check=True)

    def get_position(self) -> tuple[int, int]:
        x, y = subprocess.check_output(["cliclick", "p"]).decode().strip().split(",")
        return int(float(x)), int(float(y))

    def move_instant(self, x: int, y: int) -> None:
        self._run_cliclick(f"m:{x},{y}")

    def move_smooth(self, x: int, y: int, *, steps: int | None = None) -> None:
        sx, sy = self.get_position()
        n = steps or adaptive_steps(path_distance(sx, sy, x, y))
        cmds: list[str] = []
        for px, py in bezier_points(sx, sy, x, y, n):
            cmds.append(f"m:{px},{py}")
        cmds.append(f"m:{x},{y}")
        self._run_cliclick(*cmds)

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        *,
        fast: bool = False,
    ) -> None:
        if fast:
            self.move_instant(x, y)
        else:
            self.move_smooth(x, y)
        btn = {"left": "dd", "right": "rd", "middle": "md"}.get(button, "dd")
        for _ in range(clicks):
            self._run_cliclick(f"{btn}:{x},{y}", "w:15", f"du:{x},{y}")
            time.sleep(0.02)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.move_smooth(x1, y1)
        self._run_cliclick(f"dd:{x1},{y1}")
        sx, sy = self.get_position()
        n = adaptive_steps(path_distance(sx, sy, x2, y2))
        cmds: list[str] = []
        for px, py in bezier_points(sx, sy, x2, y2, n):
            cmds.append(f"m:{px},{py}")
        cmds.extend([f"m:{x2},{y2}", f"du:{x2},{y2}"])
        self._run_cliclick(*cmds)

    def scroll(self, dx: int, dy: int) -> None:
        if dx or dy:
            try:
                from hui_mcp.input.mac_scroll import post_scroll_wheel

                post_scroll_wheel(dx=dx, dy=dy)
                return
            except Exception:
                pass
        # Fallback: arrow keys for small incremental scroll (avoid Page Down jumps).
        if dy:
            repeats = max(1, min(8, abs(dy) // 6))
            key = "arrow-down" if dy < 0 else "arrow-up"
            for _ in range(repeats):
                self.press_key(key)
                time.sleep(0.03)
        if dx:
            key = "arrow-right" if dx > 0 else "arrow-left"
            for _ in range(max(1, abs(dx))):
                self.press_key(key)
                time.sleep(0.03)

    def press_key(self, key: str) -> None:
        k = _normalize_key(key)
        if k in _KP_KEYS:
            self._run_cliclick(f"kp:{k}")
        elif len(k) == 1:
            self._run_cliclick(f"t:{k}")
        else:
            raise ValueError(f"unsupported key: {key}")

    def hotkey(self, keys: list[str]) -> None:
        self._run_cliclick(*build_hotkey_commands(keys))

    def type_text(self, text: str) -> None:
        if len(text) > 500:
            raise ValueError("text exceeds 500 characters")
        safe = text.replace(":", "\\:")
        self._run_cliclick(f"t:{safe}")
