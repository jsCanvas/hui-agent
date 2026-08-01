"""Global Esc key listener (macOS) to cancel active Companion tasks."""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger("hui_mcp.esc_listener")

_started = False
_start_lock = threading.Lock()


def start_esc_listener() -> bool:
    """Start background Esc listener once. Returns True if running."""
    global _started
    if sys.platform != "darwin":
        return False
    with _start_lock:
        if _started:
            return True
        try:
            t = threading.Thread(target=_run_event_tap, name="esc-cancel-listener", daemon=True)
            t.start()
            _started = True
            return True
        except Exception as e:
            log.warning("esc listener failed to start: %s", e)
            return False


def _run_event_tap() -> None:
    import ctypes
    import ctypes.util

    from hui_mcp.task_cancel import on_esc_pressed

    kCGEventKeyDown = 10
    kCGKeyboardEventKeycode = 9
    kVK_Escape = 53
    kCGEventTapOptionDefault = 0
    kCGHeadInsertEventTap = 0
    kCGEventTapListenOnly = 1

    cg_path = ctypes.util.find_library("CoreGraphics")
    cf_path = ctypes.util.find_library("CoreFoundation")
    if not cg_path or not cf_path:
        log.warning("esc listener: CoreGraphics/CoreFoundation not found")
        return

    cg = ctypes.CDLL(cg_path)
    cf = ctypes.CDLL(cf_path)

    CGEventTapCallBack = ctypes.CFUNCTYPE(
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    cg.CGEventTapCreate.restype = ctypes.c_void_p
    cg.CGEventTapCreate.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint64,
        CGEventTapCallBack,
        ctypes.c_void_p,
    ]
    cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    cg.CGEventGetIntegerValueField.restype = ctypes.c_int64
    cg.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    cg.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p

    cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
    cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    cf.CFRunLoopAddSource.restype = None
    cf.CFRunLoopRun.restype = None
    try:
        common_modes = ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes")
    except ValueError:
        common_modes = None

    def callback(proxy, event_type, event, refcon):
        if event_type == kCGEventKeyDown and event:
            code = cg.CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if code == kVK_Escape:
                on_esc_pressed()
        return event

    cb = CGEventTapCallBack(callback)
    mask = 1 << kCGEventKeyDown
    tap = cg.CGEventTapCreate(
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        kCGEventTapListenOnly,
        mask,
        cb,
        None,
    )
    if not tap:
        log.warning(
            "esc listener: CGEventTapCreate failed (grant Accessibility for HuiAgent / Terminal)"
        )
        return

    run_loop_source = cg.CFMachPortCreateRunLoopSource(None, tap, 0)
    if not run_loop_source:
        log.warning("esc listener: CFMachPortCreateRunLoopSource failed")
        return
    cg.CGEventTapEnable(tap, True)

    run_loop = cf.CFRunLoopGetCurrent()
    cf.CFRunLoopAddSource(run_loop, run_loop_source, common_modes)
    log.info("esc listener active — press Esc to cancel running Companion task")
    cf.CFRunLoopRun()
