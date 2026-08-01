"""Bezier path tuning tests."""

from hui_mcp.input.smooth_path import adaptive_steps


def test_adaptive_steps_faster_profile():
    assert adaptive_steps(100) == 4
    assert adaptive_steps(500) == 14
    assert adaptive_steps(5000) == 24
