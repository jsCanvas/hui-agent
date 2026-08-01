"""Windows input via pyautogui (optional dependency)."""

from __future__ import annotations

try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore

from hui_mcp.input.smooth_path import adaptive_steps, bezier_points, path_distance

_KEY_MAP = {
    "cmd": "win",
    "super": "win",
    "ctrl": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "tab": "tab",
}


class WinInputDriver:
    def __init__(self) -> None:
        if pyautogui is None:
            raise RuntimeError("Windows input requires: pip install pyautogui")
        pyautogui.FAILSAFE = False

    def get_position(self) -> tuple[int, int]:
        p = pyautogui.position()
        return int(p.x), int(p.y)

    def move_instant(self, x: int, y: int) -> None:
        pyautogui.moveTo(x, y, duration=0)

    def move_smooth(self, x: int, y: int, *, steps: int | None = None) -> None:
        sx, sy = self.get_position()
        n = steps or adaptive_steps(path_distance(sx, sy, x, y))
        points = bezier_points(sx, sy, x, y, n)
        duration = max(0.08, n * 0.004)
        step_duration = duration / max(len(points), 1)
        for px, py in points:
            pyautogui.moveTo(px, py, duration=step_duration)
        pyautogui.moveTo(x, y)

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
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.move_smooth(x1, y1)
        pyautogui.mouseDown()
        self.move_smooth(x2, y2)
        pyautogui.mouseUp()

    def scroll(self, dx: int, dy: int) -> None:
        if dy:
            pyautogui.scroll(dy)
        if dx:
            pyautogui.hscroll(dx)

    def press_key(self, key: str) -> None:
        k = _KEY_MAP.get(key.lower(), key.lower())
        pyautogui.press(k)

    def hotkey(self, keys: list[str]) -> None:
        mapped = [_KEY_MAP.get(k.lower(), k.lower()) for k in keys]
        pyautogui.hotkey(*mapped)

    def type_text(self, text: str) -> None:
        if len(text) > 500:
            raise ValueError("text exceeds 500 characters")
        pyautogui.write(text, interval=0.02)
