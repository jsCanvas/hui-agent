"""Ring buffer for recent desktop frames (5s @ 10fps = 50 slots)."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread

from hui_mcp.capture.grabber import ScreenGrabber


@dataclass
class FrameSlot:
    index: int
    timestamp_ms: int
    filepath: Path


class FrameRingBuffer:
    capacity = 50
    fps = 10

    def __init__(self, storage_dir: Path, grabber: ScreenGrabber | None = None) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.grabber = grabber or ScreenGrabber()
        self._slots: list[FrameSlot | None] = [None] * self.capacity
        self._head = 0
        self._seq = 0
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = Thread(target=self._loop, daemon=True, name="capture-loop")
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop:
            t0 = time.time()
            try:
                png = self.grabber.grab_png()
                self._push(png)
            except Exception as e:
                print(f"[capture] grab failed: {e}", flush=True)
            elapsed = time.time() - t0
            time.sleep(max(0, interval - elapsed))

    def _push(self, png: bytes) -> FrameSlot:
        with self._lock:
            self._seq += 1
            idx = self._head % self.capacity
            path = self.storage_dir / f"ring_{idx:02d}.png"
            path.write_bytes(png)
            slot = FrameSlot(index=self._seq, timestamp_ms=int(time.time() * 1000), filepath=path)
            self._slots[idx] = slot
            self._head += 1
            return slot

    def snapshot(self) -> list[FrameSlot]:
        with self._lock:
            slots = [s for s in self._slots if s is not None]
            slots.sort(key=lambda s: s.timestamp_ms)
            return slots

    def latest_slot(self) -> FrameSlot | None:
        with self._lock:
            slots = [s for s in self._slots if s is not None]
            if not slots:
                return None
            return max(slots, key=lambda s: s.timestamp_ms)

    def materialize_to_dir(self, dest: Path | None = None) -> Path:
        dest = dest or Path(f"/tmp/hui-agent-frames-{uuid.uuid4().hex[:8]}")
        dest.mkdir(parents=True, exist_ok=True)
        slots = self.snapshot()
        frames_meta = []
        for s in slots:
            name = f"frame_{s.index:06d}_{s.timestamp_ms}.png"
            out = dest / name
            shutil.copy2(s.filepath, out)
            frames_meta.append({"file": name, "index": s.index, "timestamp_ms": s.timestamp_ms})
        info = self.grabber.monitor_info()
        manifest = {
            "version": 1,
            "captured_at_ms": int(time.time() * 1000),
            "duration_sec": min(5.0, len(slots) / self.fps),
            "fps": self.fps,
            "frame_count": len(slots),
            "monitor": {
                "id": info.id,
                "width": info.width,
                "height": info.height,
                "scale_factor": info.scale_factor,
            },
            "frames": frames_meta,
        }
        (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest
