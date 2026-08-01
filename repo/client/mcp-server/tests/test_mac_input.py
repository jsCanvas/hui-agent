"""macOS cliclick hotkey command tests."""

from hui_mcp.input.mac import build_hotkey_commands


def test_cmd_f_hotkey():
    assert build_hotkey_commands(["cmd", "f"]) == ["w:40", "kd:cmd", "t:f", "ku:cmd"]


def test_cmd_shift_z():
    assert build_hotkey_commands(["cmd", "shift", "z"]) == [
        "w:40",
        "kd:cmd,shift",
        "t:z",
        "ku:cmd,shift",
    ]


def test_enter_only():
    assert build_hotkey_commands(["enter"]) == ["w:40", "kp:return"]


def test_cmd_enter():
    assert build_hotkey_commands(["ctrl", "enter"]) == [
        "w:40",
        "kd:ctrl",
        "kp:return",
        "ku:ctrl",
    ]


def test_mac_scroll_uses_native_wheel(monkeypatch):
    from hui_mcp.input.mac import MacInputDriver

    calls: list[tuple[int, int]] = []

    def fake_wheel(*, dx: int = 0, dy: int = 0) -> None:
        calls.append((dx, dy))

    monkeypatch.setattr(
        "hui_mcp.input.mac_scroll.post_scroll_wheel",
        fake_wheel,
    )
    MacInputDriver().scroll(0, -24)
    assert calls == [(0, -24)]


def test_mac_scroll_keyboard_fallback(monkeypatch):
    from hui_mcp.input.mac import MacInputDriver

    calls: list[str] = []

    def fail_wheel(*, dx: int = 0, dy: int = 0) -> None:
        raise OSError("no quartz")

    def fake_press(self, key: str) -> None:
        calls.append(key)

    monkeypatch.setattr(
        "hui_mcp.input.mac_scroll.post_scroll_wheel",
        fail_wheel,
    )
    monkeypatch.setattr(MacInputDriver, "press_key", fake_press)
    MacInputDriver().scroll(0, -24)
    assert calls == ["arrow-down"] * 4


def test_mac_scroll_small_uses_arrows(monkeypatch):
    from hui_mcp.input.mac import MacInputDriver

    calls: list[str] = []

    def fail_wheel(*, dx: int = 0, dy: int = 0) -> None:
        raise OSError("no quartz")

    def fake_press(self, key: str) -> None:
        calls.append(key)

    monkeypatch.setattr(
        "hui_mcp.input.mac_scroll.post_scroll_wheel",
        fail_wheel,
    )
    monkeypatch.setattr(MacInputDriver, "press_key", fake_press)
    MacInputDriver().scroll(0, -3)
    assert calls == ["arrow-down"]
