from __future__ import annotations

import ctypes
from contextlib import contextmanager
import os
import time

from ctypes import wintypes

from core.tool_result import ToolResult


def _configurar_user32_api(user32):
    """Configura apenas as APIs de input usadas por este modulo."""
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL

    user32.mouse_event.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t
    ]
    user32.mouse_event.restype = None

    user32.keybd_event.argtypes = [
        wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t
    ]
    user32.keybd_event.restype = None

    if hasattr(user32, "SetThreadDpiAwarenessContext"):
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p

    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int


def _user32():
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    _configurar_user32_api(user32)
    return user32


def controle_midia_windows(acao):
    if os.name != "nt":
        return "Controle de midia so esta disponivel no Windows."

    mapa = {
        "play_pause": 0xB3,
        "play/pause": 0xB3,
        "pausar": 0xB3,
        "reproduzir": 0xB3,
        "proxima": 0xB0,
        "proximo": 0xB0,
        "next": 0xB0,
        "anterior": 0xB1,
        "previous": 0xB1,
        "prev": 0xB1,
        "parar": 0xB2,
        "stop": 0xB2,
    }
    chave = str(acao).strip().lower()
    vk = mapa.get(chave)
    if vk is None:
        return ToolResult.failure(
            "Acao de midia invalida. Use play_pause, proxima, anterior ou parar.",
            error_code="media_action_invalid",
        )

    try:
        _pressionar_vk(vk, soltura=False)
        _pressionar_vk(vk, soltura=True)
        nomes = {
            0xB3: "play/pause",
            0xB0: "próxima música",
            0xB1: "música anterior",
            0xB2: "parar",
        }
        return f"Comando de midia enviado: {nomes[vk]}."
    except Exception as erro:
        return f"Nao consegui enviar o comando de midia: {erro}"

_WINDOWS_VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "arrowleft": 0x25,
    "up": 0x26,
    "arrowup": 0x26,
    "right": 0x27,
    "arrowright": 0x27,
    "down": 0x28,
    "arrowdown": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "windows": 0x5B,
    "menu": 0x5D,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}

def _windows_vk(tecla):
    nome = str(tecla).strip().lower()
    if nome in _WINDOWS_VK:
        return _WINDOWS_VK[nome]
    if len(nome) == 1:
        codigo = ord(nome.upper())
        if 0 <= codigo <= 0xFF:
            return codigo
    return None

def _pressionar_vk(vk, soltura=False):
    if os.name != "nt":
        return False
    user32 = _user32()
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if soltura else 0, 0)
    return True

def pressionar_tecla_windows(tecla):
    if os.name != "nt":
        return "Controle de teclado global so esta disponivel no Windows."

    partes = [parte.strip() for parte in str(tecla).split("+") if parte.strip()]
    if not partes:
        return "Tecla vazia."

    vks = []
    for parte in partes:
        vk = _windows_vk(parte)
        if vk is None:
            return f"Nao reconheco a tecla global '{parte}'."
        vks.append(vk)

    try:
        for vk in vks:
            _pressionar_vk(vk, soltura=False)
        for vk in reversed(vks):
            _pressionar_vk(vk, soltura=True)
        return f"Tecla global pressionada: {tecla}"
    except Exception as erro:
        return f"Nao consegui pressionar a tecla global: {erro}"

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


@contextmanager
def _contexto_dpi_per_monitor_windows(user32):
    """Executa APIs de tela em coordenadas físicas, quando o Windows oferece PMv2."""
    setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if setter is None:
        yield False
        return

    try:
        anterior = setter(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        yield False
        return

    aplicado = bool(anterior)
    try:
        yield aplicado
    finally:
        if anterior:
            try:
                setter(anterior)
            except Exception:
                pass


def _limites_tela_virtual_windows(user32):
    """Retorna limites da área de trabalho virtual em coordenadas físicas."""
    with _contexto_dpi_per_monitor_windows(user32):
        origem_x = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
        origem_y = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
        largura = int(user32.GetSystemMetrics(78))   # SM_CXVIRTUALSCREEN
        altura = int(user32.GetSystemMetrics(79))    # SM_CYVIRTUALSCREEN
    return origem_x, origem_y, largura, altura


def mover_mouse_windows(x, y):
    if os.name != "nt":
        return "Controle do mouse global so esta disponivel no Windows."

    try:
        x = int(x)
        y = int(y)
        user32 = _user32()
        origem_x, origem_y, largura, altura = _limites_tela_virtual_windows(user32)
        limite_x = origem_x + largura
        limite_y = origem_y + altura
        if x < origem_x or y < origem_y or x >= limite_x or y >= limite_y:
            return (
                f"Coordenadas fora da area de trabalho virtual: ({x}, {y}). "
                f"Limites detectados: x={origem_x}..{limite_x - 1}, "
                f"y={origem_y}..{limite_y - 1}."
            )
        if not user32.SetCursorPos(x, y):
            return "Nao consegui mover o mouse."
        return f"Mouse movido para ({x}, {y})."
    except Exception as erro:
        return f"Nao consegui mover o mouse: {erro}"

def clicar_mouse_windows(x, y, botao="esquerdo", descricao=""):
    if os.name != "nt":
        return "Controle do mouse global so esta disponivel no Windows."

    try:
        x = int(x)
        y = int(y)
        user32 = _user32()
        origem_x, origem_y, largura, altura = _limites_tela_virtual_windows(user32)
        limite_x = origem_x + largura
        limite_y = origem_y + altura
        if x < origem_x or y < origem_y or x >= limite_x or y >= limite_y:
            return (
                f"Coordenadas fora da area de trabalho virtual: ({x}, {y}). "
                f"Limites detectados: x={origem_x}..{limite_x - 1}, "
                f"y={origem_y}..{limite_y - 1}."
            )
        if not user32.SetCursorPos(x, y):
            return "Nao consegui posicionar o mouse."

        button = str(botao).strip().lower()
        events = {
            "esquerdo": (0x0002, 0x0004),
            "left": (0x0002, 0x0004),
            "direito": (0x0008, 0x0010),
            "right": (0x0008, 0x0010),
            "meio": (0x0020, 0x0040),
            "middle": (0x0020, 0x0040),
        }
        down_up = events.get(button)
        if down_up is None:
            return ToolResult.failure(
                "Botao invalido. Use esquerdo, direito ou meio.",
                error_code="mouse_button_invalid",
            )
        MOUSEEVENTF = getattr(user32, "mouse_event")
        MOUSEEVENTF(down_up[0], 0, 0, 0, 0)
        time.sleep(0.02)
        MOUSEEVENTF(down_up[1], 0, 0, 0, 0)
        detalhe = f" ({descricao})" if descricao else ""
        return f"Clique global executado em ({x}, {y}), botao {button}{detalhe}."
    except Exception as erro:
        return f"Nao consegui clicar com o mouse: {erro}"


def arrastar_mouse_windows(
    x_inicial,
    y_inicial,
    x_final,
    y_final,
    botao="esquerdo",
    duracao_ms=300,
    descricao="",
):
    """Arrasta o mouse entre duas coordenadas globais da area de trabalho."""
    if os.name != "nt":
        return "Controle do mouse global so esta disponivel no Windows."

    try:
        x_inicial = int(x_inicial)
        y_inicial = int(y_inicial)
        x_final = int(x_final)
        y_final = int(y_final)
        duracao_ms = int(duracao_ms)
    except (TypeError, ValueError):
        return ToolResult.failure(
            "Coordenadas e duracao do arraste devem ser inteiros.",
            error_code="drag_arguments_invalid",
        )

    if duracao_ms < 50 or duracao_ms > 3000:
        return ToolResult.failure(
            "A duracao do arraste deve ficar entre 50 e 3000 ms.",
            error_code="drag_duration_invalid",
        )

    try:
        user32 = _user32()
        origem_x, origem_y, largura, altura = _limites_tela_virtual_windows(user32)
        limite_x = origem_x + largura
        limite_y = origem_y + altura

        def dentro_da_area(x, y):
            return origem_x <= x < limite_x and origem_y <= y < limite_y

        for nome_ponto, x, y in (
            ("origem", x_inicial, y_inicial),
            ("destino", x_final, y_final),
        ):
            if not dentro_da_area(x, y):
                return ToolResult.failure(
                    (
                        f"Coordenadas de {nome_ponto} fora da area de trabalho virtual: "
                        f"({x}, {y}). Limites detectados: "
                        f"x={origem_x}..{limite_x - 1}, "
                        f"y={origem_y}..{limite_y - 1}."
                    ),
                    error_code="drag_coordinates_out_of_bounds",
                )

        button = str(botao).strip().lower()
        events = {
            "esquerdo": (0x0002, 0x0004),
            "left": (0x0002, 0x0004),
            "direito": (0x0008, 0x0010),
            "right": (0x0008, 0x0010),
            "meio": (0x0020, 0x0040),
            "middle": (0x0020, 0x0040),
        }
        down_up = events.get(button)
        if down_up is None:
            return ToolResult.failure(
                "Botao invalido. Use esquerdo, direito ou meio.",
                error_code="mouse_button_invalid",
            )

        if not user32.SetCursorPos(x_inicial, y_inicial):
            return ToolResult.failure(
                "Nao consegui posicionar o mouse no inicio do arraste.",
                error_code="drag_start_position_failed",
            )

        mouse_event = getattr(user32, "mouse_event")
        mouse_event(down_up[0], 0, 0, 0, 0)

        try:
            distancia = max(abs(x_final - x_inicial), abs(y_final - y_inicial))
            passos = max(1, min(120, int(distancia / 8) or 1))
            intervalo = duracao_ms / 1000 / passos

            for passo in range(1, passos + 1):
                fracao = passo / passos
                x = round(x_inicial + (x_final - x_inicial) * fracao)
                y = round(y_inicial + (y_final - y_inicial) * fracao)
                if not user32.SetCursorPos(x, y):
                    return ToolResult.failure(
                        f"Nao consegui mover o mouse durante o arraste para ({x}, {y}).",
                        error_code="drag_move_failed",
                    )
                if intervalo > 0:
                    time.sleep(intervalo)
        finally:
            mouse_event(down_up[1], 0, 0, 0, 0)

        detalhe = f" ({descricao})" if descricao else ""
        return (
            f"Arraste global executado de ({x_inicial}, {y_inicial}) "
            f"para ({x_final}, {y_final}), botao {button}, "
            f"duracao {duracao_ms} ms{detalhe}."
        )
    except Exception as erro:
        return f"Nao consegui arrastar com o mouse: {erro}"

