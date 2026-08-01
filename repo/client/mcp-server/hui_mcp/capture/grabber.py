"""Primary monitor screen capture via mss."""

from __future__ import annotations

from dataclasses import dataclass

import mss
import numpy as np
from PIL import Image


@dataclass
class MonitorInfo:
    id: int
    width: int
    height: int
    scale_factor: float
    origin_x: int
    origin_y: int


class ScreenGrabber:
    """Capture primary monitor; coordinates in logical points where possible."""

    def __init__(self, monitor_index: int = 1) -> None:
        self._monitor_index = monitor_index
        self._sct: mss.mss | None = None
        self._last_size = (1920, 1080)

    def _ensure(self) -> mss.mss:
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def _monitor(self) -> dict:
        sct = self._ensure()
        mons = sct.monitors
        idx = self._monitor_index if self._monitor_index < len(mons) else 1
        return mons[idx]

    def grab_png(self) -> bytes:
        sct = self._ensure()
        mon = self._monitor()
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self._last_size = img.size
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def grab_array(self) -> np.ndarray:
        sct = self._ensure()
        mon = self._monitor()
        raw = np.asarray(sct.grab(mon))
        frame = np.ascontiguousarray(raw[:, :, :3])
        self._last_size = (frame.shape[1], frame.shape[0])
        return frame

    def monitor_info(self) -> MonitorInfo:
        mon = self._monitor()
        w, h = mon["width"], mon["height"]
        # Heuristic scale for Retina: compare with system could be added later
        scale = 2.0 if w >= 2560 else 1.0
        return MonitorInfo(
            id=self._monitor_index,
            width=w,
            height=h,
            scale_factor=scale,
            origin_x=mon.get("left", 0),
            origin_y=mon.get("top", 0),
        )
