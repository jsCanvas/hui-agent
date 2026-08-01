"""Cross-platform input driver protocol."""

from __future__ import annotations

import platform
import sys
from typing import Protocol


class InputDriver(Protocol):
    def get_position(self) -> tuple[int, int]: ...
    def move_smooth(self, x: int, y: int, *, steps: int | None = None) -> None: ...
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def press_key(self, key: str) -> None: ...
    def hotkey(self, keys: list[str]) -> None: ...
    def type_text(self, text: str) -> None: ...


def create_driver() -> InputDriver:
    system = platform.system()
    if system == "Darwin":
        from hui_mcp.input.mac import MacInputDriver

        return MacInputDriver()
    if system == "Windows":
        from hui_mcp.input.win import WinInputDriver

        return WinInputDriver()
    raise RuntimeError(f"Unsupported platform: {system}")
