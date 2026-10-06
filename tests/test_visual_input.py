from __future__ import annotations

import os

import pytest

from tools import windows


@pytest.mark.skipif(os.name != "nt", reason="arraste global exige Windows")
def test_arrastar_mouse_windows_executa_gesto_completo(monkeypatch):
    class FakeUser32:
        def __init__(self):
            self.positions = []
            self.events = []

        def GetSystemMetrics(self, index):
            return {
                76: 0,
                77: 0,
                78: 1920,
                79: 1080,
            }[index]

        def SetCursorPos(self, x, y):
            self.positions.append((x, y))
            return True

        def mouse_event(self, event, _dx, _dy, _data, _extra):
            self.events.append(event)

    fake = FakeUser32()
    monkeypatch.setattr(windows, "_user32", lambda: fake)

    result = windows.arrastar_mouse_windows(
        100,
        100,
        120,
        110,
        botao="esquerdo",
        duracao_ms=50,
        descricao="item de teste",
    )

    assert "Arraste global executado" in result
    assert fake.positions[0] == (100, 100)
    assert fake.positions[-1] == (120, 110)
    assert fake.events == [0x0002, 0x0004]


@pytest.mark.skipif(os.name != "nt", reason="arraste global exige Windows")
def test_arrastar_mouse_windows_rejeita_origem_fora_da_area_virtual(monkeypatch):
    class FakeUser32:
        def GetSystemMetrics(self, index):
            return {
                76: 0,
                77: 0,
                78: 1920,
                79: 1080,
            }[index]

    monkeypatch.setattr(windows, "_user32", lambda: FakeUser32())

    result = windows.arrastar_mouse_windows(
        -1,
        100,
        120,
        110,
        botao="esquerdo",
        duracao_ms=50,
        descricao="item de teste",
    )

    assert result.ok is False
    assert result.error_code == "drag_coordinates_out_of_bounds"


@pytest.mark.skipif(os.name != "nt", reason="DPI do Windows exige Windows")
def test_limites_tela_virtual_tenta_contexto_per_monitor_dpi(monkeypatch):
    class FakeUser32:
        def __init__(self):
            self.dpi_calls = []

        def SetThreadDpiAwarenessContext(self, context):
            self.dpi_calls.append(context)
            if len(self.dpi_calls) == 1:
                return object()
            return object()

        def GetSystemMetrics(self, index):
            return {
                76: -1920,
                77: -300,
                78: 3840,
                79: 1740,
            }[index]

    fake = FakeUser32()
    origem = windows._limites_tela_virtual_windows(fake)

    assert origem == (-1920, -300, 3840, 1740)
    assert len(fake.dpi_calls) == 2


@pytest.mark.skipif(os.name != "nt", reason="DPI do Windows exige Windows")
def test_arraste_com_origem_virtual_negativa_continua_valido(monkeypatch):
    class FakeUser32:
        def __init__(self):
            self.positions = []
            self.events = []

        def GetSystemMetrics(self, index):
            return {
                76: -1920,
                77: -300,
                78: 3840,
                79: 1740,
            }[index]

        def SetCursorPos(self, x, y):
            self.positions.append((x, y))
            return True

        def mouse_event(self, event, _dx, _dy, _data, _extra):
            self.events.append(event)

    fake = FakeUser32()
    monkeypatch.setattr(windows, "_user32", lambda: fake)

    result = windows.arrastar_mouse_windows(
        -100,
        50,
        200,
        300,
        botao="esquerdo",
        duracao_ms=50,
        descricao="teste de coordenadas virtuais",
    )

    assert result.ok is True
    assert fake.positions[0] == (-100, 50)
    assert fake.positions[-1] == (200, 300)
    assert fake.events == [0x0002, 0x0004]
