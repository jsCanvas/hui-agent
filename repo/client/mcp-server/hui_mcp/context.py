"""Shared runtime state for MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from hui_mcp.capture.grabber import ScreenGrabber
from hui_mcp.capture.ring_buffer import FrameRingBuffer
from hui_mcp.config import AppConfig
from hui_mcp.input.driver import InputDriver, create_driver


@dataclass
class AppContext:
    config: AppConfig
    grabber: ScreenGrabber = field(default_factory=ScreenGrabber)
    ring: FrameRingBuffer | None = None
    driver: InputDriver | None = None

    def ensure_ring(self) -> FrameRingBuffer:
        if self.ring is None:
            ring_dir = self.config.frame_dir / "ring"
            self.ring = FrameRingBuffer(ring_dir, self.grabber)
            self.ring.start()
        return self.ring

    def ensure_driver(self) -> InputDriver:
        if self.driver is None:
            self.driver = create_driver()
        return self.driver
