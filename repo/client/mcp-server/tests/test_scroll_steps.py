"""Tests for incremental scroll helpers."""

from __future__ import annotations

from hui_mcp.input.scroll_steps import scroll_incremental


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def scroll(self, dx: int, dy: int) -> None:
        self.calls.append((dx, dy))


def test_scroll_incremental_splits_dy():
    driver = FakeDriver()
    scroll_incremental(driver, 0, -24, step=12, pause_sec=0)
    assert driver.calls == [(0, -12), (0, -12)]
