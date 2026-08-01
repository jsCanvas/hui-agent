"""Native macOS scroll wheel via Quartz (works in Chrome/Feishu docs)."""

from __future__ import annotations

import ctypes
import ctypes.util
import time

_kCGHIDEventTap = 0
_kCGScrollEventUnitLine = 1
_kCGScrollEventUnitPixel = 0


def _load_core_graphics():
    path = ctypes.util.find_library("CoreGraphics")
    if not path:
        raise OSError("CoreGraphics not found")
    lib = ctypes.CDLL(path)
    lib.CGEventCreateScrollWheelEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
    lib.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    lib.CGEventPost.restype = None
    return lib


def post_scroll_wheel(*, dx: int = 0, dy: int = 0) -> None:
    """Post scroll wheel at cursor. dy<0 scrolls down, dy>0 up; dx for horizontal."""
    if dx == 0 and dy == 0:
        return
    lib = _load_core_graphics()

    def emit(unit: int, vertical: int, horizontal: int = 0) -> None:
        if horizontal:
            ev = lib.CGEventCreateScrollWheelEvent(
                None, unit, 2, vertical, horizontal
            )
        else:
            ev = lib.CGEventCreateScrollWheelEvent(None, unit, 1, vertical, 0)
        if not ev:
            raise OSError("CGEventCreateScrollWheelEvent failed")
        lib.CGEventPost(_kCGHIDEventTap, ev)

    if dy:
        # dy=-24 → ~8 wheel ticks × 60px (visible in Feishu/Chrome)
        ticks = max(1, min(16, abs(dy) // 3))
        sign = -1 if dy < 0 else 1
        for _ in range(ticks):
            emit(_kCGScrollEventUnitPixel, sign * 60, 0)
            time.sleep(0.06)
    if dx:
        ticks = max(1, min(12, abs(dx) // 4))
        sign = 1 if dx > 0 else -1
        for _ in range(ticks):
            emit(_kCGScrollEventUnitPixel, 0, sign * 40)
            time.sleep(0.04)
