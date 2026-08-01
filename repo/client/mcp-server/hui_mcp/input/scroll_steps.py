"""Incremental scroll helpers — small steps instead of page jumps."""

from __future__ import annotations

import time
from typing import Protocol


class ScrollDriver(Protocol):
    def scroll(self, dx: int, dy: int) -> None: ...


def scroll_incremental(
    driver: ScrollDriver,
    dx: int,
    dy: int,
    *,
    step: int = 12,
    pause_sec: float = 0.06,
) -> None:
    """Split dy/dx into small wheel steps (reading-friendly, no Page Down)."""
    if dy:
        sign = -1 if dy < 0 else 1
        remaining = abs(dy)
        first = True
        while remaining > 0:
            chunk = min(step, remaining)
            driver.scroll(dx if first else 0, sign * chunk)
            first = False
            remaining -= chunk
            if remaining > 0 and pause_sec:
                time.sleep(pause_sec)
        return
    if dx:
        sign = -1 if dx < 0 else 1
        remaining = abs(dx)
        while remaining > 0:
            chunk = min(step, remaining)
            driver.scroll(sign * chunk, 0)
            remaining -= chunk
            if remaining > 0 and pause_sec:
                time.sleep(pause_sec)
