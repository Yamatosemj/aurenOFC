from __future__ import annotations

from tools import browser, browser_navigation


class _FakeMouse:
    def __init__(self) -> None:
        self.calls = []

    def wheel(self, x, y) -> None:
        self.calls.append((x, y))


class _FakePage:
    def __init__(self) -> None:
        self.mouse = _FakeMouse()
        self.scroll_values = iter([0, 900])

    def evaluate(self, script: str):
        if "window.scrollY" in script:
            return next(self.scroll_values)
        if "document.body?.scrollHeight" in script:
            return 3000
        if "window.innerHeight" in script:
            return 900
        raise AssertionError(f"script inesperado: {script}")


def test_scroll_returns_structured_before_and_after_state(monkeypatch):
    page = _FakePage()
    monkeypatch.setattr(browser, "obter_pagina", lambda: page)

    result = browser_navigation.rolar_pagina("baixo")

    assert result.ok is True
    assert result.tool_name == "rolar_pagina"
    assert result.data["direcao"] == "baixo"
    assert result.data["scroll_y_antes"] == 0.0
    assert result.data["scroll_y_depois"] == 900.0
    assert result.data["scroll_height"] == 3000.0
    assert result.data["viewport_height"] == 900.0
    assert result.data["alvo"] == ""
    assert result.data["alvo_encontrado"] is None
    assert page.mouse.calls == [(0, 900)]


def test_scroll_invalid_direction_remains_structured_failure():
    result = browser_navigation.rolar_pagina("diagonal")

    assert result.ok is False
    assert result.error_code == "scroll_direction_invalid"
