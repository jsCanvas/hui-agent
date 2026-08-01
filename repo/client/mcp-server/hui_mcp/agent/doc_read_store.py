"""Background OCR read jobs — in-memory + persisted under ~/.hui-agent/doc-read/."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DOC_READ_DIR = Path.home() / ".hui-agent" / "doc-read"


@dataclass
class DocReadSnapshot:
    task_id: str
    section_query: str
    status: str = "pending"  # pending | running | done | error | skipped
    progress: list[dict[str, str]] = field(default_factory=list)
    page_count: int = 0
    ocr_text: str = ""
    ocr_preview: str = ""
    edge_outline: str = ""
    edge_model_used: str = ""
    pages: list[str] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self, *, include_full_ocr: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "task_id": self.task_id,
            "section_query": self.section_query,
            "status": self.status,
            "progress": list(self.progress),
            "page_count": self.page_count,
            "ocr_preview": self.ocr_preview,
            "edge_outline": self.edge_outline,
            "edge_model_used": self.edge_model_used,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if include_full_ocr:
            body["ocr_text"] = self.ocr_text
            body["pages"] = list(self.pages)
        return body

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocReadSnapshot:
        return cls(
            task_id=str(data.get("task_id") or ""),
            section_query=str(data.get("section_query") or ""),
            status=str(data.get("status") or "pending"),
            progress=list(data.get("progress") or []),
            page_count=int(data.get("page_count") or 0),
            ocr_text=str(data.get("ocr_text") or ""),
            ocr_preview=str(data.get("ocr_preview") or ""),
            edge_outline=str(data.get("edge_outline") or ""),
            edge_model_used=str(data.get("edge_model_used") or ""),
            pages=list(data.get("pages") or []),
            error=str(data.get("error") or ""),
            started_at=float(data.get("started_at") or time.time()),
            finished_at=data.get("finished_at"),
        )


def _load_from_disk(task_id: str) -> DocReadSnapshot | None:
    path = DOC_READ_DIR / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DocReadSnapshot.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


_STATUS_RANK = {"pending": 0, "running": 1, "skipped": 2, "error": 3, "done": 4}


def _pick_newer(a: DocReadSnapshot, b: DocReadSnapshot) -> DocReadSnapshot:
    ra = _STATUS_RANK.get(a.status, 0)
    rb = _STATUS_RANK.get(b.status, 0)
    if ra != rb:
        return a if ra > rb else b
    fa = a.finished_at or a.started_at
    fb = b.finished_at or b.started_at
    return a if fa >= fb else b


def _persist(snap: DocReadSnapshot) -> None:
    if not snap.task_id:
        return
    try:
        DOC_READ_DIR.mkdir(parents=True, exist_ok=True)
        path = DOC_READ_DIR / f"{snap.task_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(snap.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        pass


def load_doc_read_snapshot(task_id: str) -> DocReadSnapshot | None:
    """Load from Daemon memory and/or disk (MCP stdio shares disk with Daemon)."""
    mem = get_doc_read_store().get(task_id)
    disk = _load_from_disk(task_id)
    if mem and disk:
        return _pick_newer(mem, disk)
    return mem or disk


class DocReadStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, DocReadSnapshot] = {}

    def start(self, task_id: str, section_query: str) -> DocReadSnapshot:
        snap = DocReadSnapshot(task_id=task_id, section_query=section_query, status="running")
        with self._lock:
            self._jobs[task_id] = snap
        _persist(snap)
        return snap

    def skip(self, task_id: str, reason: str) -> None:
        with self._lock:
            snap = self._jobs.get(task_id)
            if snap is None:
                snap = DocReadSnapshot(task_id=task_id, section_query="", status="skipped")
                self._jobs[task_id] = snap
            snap.status = "skipped"
            snap.error = reason
            snap.finished_at = time.time()
            _persist(snap)

    def append_progress(self, task_id: str, step: str, message: str) -> None:
        with self._lock:
            snap = self._jobs.get(task_id)
            if not snap:
                return
            snap.progress.append({"step": step, "message": message})
            _persist(snap)

    def finish(
        self,
        task_id: str,
        *,
        ocr_text: str,
        ocr_preview: str,
        edge_outline: str,
        pages: list[str],
        ok: bool = True,
        error: str = "",
        edge_model_used: str = "",
    ) -> None:
        with self._lock:
            snap = self._jobs.get(task_id)
            if snap is None:
                snap = _load_from_disk(task_id) or DocReadSnapshot(
                    task_id=task_id,
                    section_query="",
                    status="running",
                )
                self._jobs[task_id] = snap
            snap.status = "done" if ok else "error"
            snap.ocr_text = ocr_text
            snap.ocr_preview = ocr_preview
            snap.edge_outline = edge_outline
            snap.edge_model_used = edge_model_used
            snap.pages = list(pages)
            snap.page_count = len(pages)
            snap.error = error
            snap.finished_at = time.time()
            _persist(snap)

    def get(self, task_id: str) -> DocReadSnapshot | None:
        with self._lock:
            snap = self._jobs.get(task_id)
            if snap is None:
                return None
            return DocReadSnapshot(
                task_id=snap.task_id,
                section_query=snap.section_query,
                status=snap.status,
                progress=list(snap.progress),
                page_count=snap.page_count,
                ocr_text=snap.ocr_text,
                ocr_preview=snap.ocr_preview,
                edge_outline=snap.edge_outline,
                edge_model_used=snap.edge_model_used,
                pages=list(snap.pages),
                error=snap.error,
                started_at=snap.started_at,
                finished_at=snap.finished_at,
            )

    def clear(self, task_id: str) -> None:
        with self._lock:
            self._jobs.pop(task_id, None)
        try:
            (DOC_READ_DIR / f"{task_id}.json").unlink(missing_ok=True)
        except OSError:
            pass


_store = DocReadStore()


def get_doc_read_store() -> DocReadStore:
    return _store
