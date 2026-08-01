"""Bezier smooth mouse paths for agent mode (no random jitter)."""

from __future__ import annotations

import math


def ease(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def adaptive_steps(distance: float, *, min_steps: int = 4, max_steps: int = 24) -> int:
    """Fewer steps + shorter pauses = faster but still smooth Bezier motion."""
    return max(min_steps, min(max_steps, int(distance / 35)))


def bezier_points(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    steps: int,
    *,
    curve_offset: float = 0.0,
) -> list[tuple[int, int]]:
    mx = (sx + tx) / 2 + curve_offset
    my = (sy + ty) / 2 - 20 + curve_offset
    points: list[tuple[int, int]] = []
    for i in range(1, steps + 1):
        t = ease(i / steps)
        u = 1 - t
        x = u * u * sx + 2 * u * t * mx + t * t * tx
        y = u * u * sy + 2 * u * t * my + t * t * ty
        points.append((int(round(x)), int(round(y))))
    return points


def path_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)
