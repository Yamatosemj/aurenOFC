from __future__ import annotations

import ctypes
from ctypes import wintypes
import os



def _configurar_user32_api(user32):
    """Configura as assinaturas Win64 usadas pelo controle do Windows."""
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.GetDesktopWindow.argtypes = []
    user32.GetDesktopWindow.restype = wintypes.HWND

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int

    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL

    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL

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

    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
    ]
    user32.PostMessageW.restype = wintypes.BOOL

    if hasattr(user32, "SetThreadDpiAwarenessContext"):
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p

def _user32():
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    _configurar_user32_api(user32)
    return user32

from tools.windows_processes import _nome_executavel_por_pid_windows, encerrar_processo_windows, listar_processos_windows

from tools.windows_system import _status_windows, obter_status_windows

from tools.windows_window import (
    _enumerar_janelas_windows,
    _encontrar_janela_windows_sem_cache,
    _titulo_atual_da_janela_windows,
    _WINDOW_TARGET_CACHE,
    _encontrar_janela_windows,
    _processo_da_janela_windows,
    listar_janelas_windows,
    focar_janela_windows,
    minimizar_janela_windows,
    maximizar_janela_windows,
    obter_geometria_janela_windows,
    mover_janela_windows,
    redimensionar_janela_windows,
    restaurar_janela_windows,
    fechar_janela_windows,
)

from tools.windows_uia import (
    _ui_automation_hwnd_int,
    _executar_ui_automation,
    _ui_automation_janela,
    clicar_elemento_windows,
    inspecionar_interface_windows,
    preencher_elemento_windows,
    alternar_elemento_windows,
    selecionar_elemento_windows,
)

from tools.windows_audio import definir_mudo_windows, definir_volume_windows, obter_audio_windows

from tools.windows_input import (
    _contexto_dpi_per_monitor_windows,
    _limites_tela_virtual_windows,
    _pressionar_vk,
    controle_midia_windows,
    pressionar_tecla_windows,
    mover_mouse_windows,
    clicar_mouse_windows,
    arrastar_mouse_windows,
)

from tools.windows_clipboard import definir_area_transferencia_windows, ler_area_transferencia_windows
from tools.windows_screenshot import capturar_tela_windows

