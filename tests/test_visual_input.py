from __future__ import annotations

import os

import pytest

from core.vision import image_point_to_virtual_screen
from tools import windows, windows_input


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
    monkeypatch.setattr(windows_input, "_user32", lambda: fake)

    result = windows.arrastar_mouse_windows(
        100,
        100,
        120,
        110,
        botao="esquerdo",
        duracao_ms=50,
        descricao="item de teste",
    )

    assert "Arraste global executado" in result.message
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

    monkeypatch.setattr(windows_input, "_user32", lambda: FakeUser32())

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
    monkeypatch.setattr(windows_input, "_user32", lambda: fake)

    result = windows.arrastar_mouse_windows(
        -100,
        50,
        200,
        300,
        botao="esquerdo",
        duracao_ms=50,
        descricao="teste de coordenadas virtuais",
    )

    assert "Arraste global executado" in str(result)
    assert fake.positions[0] == (-100, 50)
    assert fake.positions[-1] == (200, 300)
    assert fake.events == [0x0002, 0x0004]


@pytest.mark.skipif(os.name != "nt", reason="clique global exige Windows")
def test_clique_recebe_coordenada_convertida_da_imagem(monkeypatch):
    class FakeUser32:
        def __init__(self):
            self.positions = []
            self.events = []

        def GetSystemMetrics(self, index):
            return {
                76: -1920,
                77: 0,
                78: 3840,
                79: 1080,
            }[index]

        def SetCursorPos(self, x, y):
            self.positions.append((x, y))
            return True

        def mouse_event(self, event, _dx, _dy, _data, _extra):
            self.events.append(event)

    fake = FakeUser32()
    monkeypatch.setattr(windows_input, "_user32", lambda: fake)

    x, y = image_point_to_virtual_screen(
        960,
        270,
        image_width=1920,
        image_height=540,
        virtual_screen_x=-1920,
        virtual_screen_y=0,
        virtual_screen_width=3840,
        virtual_screen_height=1080,
    )
    # O ponto central da imagem 1920x540 cai no centro físico da área virtual.
    assert (x, y) == (0, 540)

    result = windows.clicar_mouse_windows(
        x,
        y,
        botao="esquerdo",
        descricao="ponto convertido da visao",
    )
    assert "Clique global executado" in str(result)
    assert fake.positions == [(0, 540)]
    assert fake.events == [0x0002, 0x0004]


@pytest.mark.skipif(os.name != "nt", reason="arraste global exige Windows")
def test_arraste_usa_duas_coordenadas_convertidas_da_imagem(monkeypatch):
    class FakeUser32:
        def __init__(self):
            self.positions = []
            self.events = []

        def GetSystemMetrics(self, index):
            return {
                76: -1920,
                77: -300,
                78: 3840,
                79: 1800,
            }[index]

        def SetCursorPos(self, x, y):
            self.positions.append((x, y))
            return True

        def mouse_event(self, event, _dx, _dy, _data, _extra):
            self.events.append(event)

    fake = FakeUser32()
    monkeypatch.setattr(windows_input, "_user32", lambda: fake)

    origem = image_point_to_virtual_screen(
        480,
        270,
        image_width=960,
        image_height=540,
        virtual_screen_x=-1920,
        virtual_screen_y=-300,
        virtual_screen_width=1920,
        virtual_screen_height=1080,
    )
    destino = image_point_to_virtual_screen(
        720,
        405,
        image_width=960,
        image_height=540,
        virtual_screen_x=-1920,
        virtual_screen_y=-300,
        virtual_screen_width=1920,
        virtual_screen_height=1080,
    )

    assert origem == (-960, 240)
    assert destino == (-480, 510)

    result = windows.arrastar_mouse_windows(
        *origem,
        *destino,
        botao="esquerdo",
        duracao_ms=50,
        descricao="arraste com pontos convertidos da visao",
    )
    assert "Arraste global executado" in str(result)
    assert fake.positions[0] == origem
    assert fake.positions[-1] == destino
    assert fake.events == [0x0002, 0x0004]
