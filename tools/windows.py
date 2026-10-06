from __future__ import annotations

import base64
import ctypes
from contextlib import contextmanager
from ctypes import wintypes
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import tempfile
import time
from datetime import datetime

from core.utils import normalizar_nome, similaridade_nome
from core.tool_result import ToolResult


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

def _nome_executavel_por_pid_windows(pid):
    """Retorna apenas o nome do executavel de um PID usando APIs Win64 seguras."""
    if os.name != "nt" or not pid:
        return ""

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    ]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        wintypes.LPWSTR,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        wintypes.DWORD(int(pid)),
    )
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(1024)
        tamanho = ctypes.c_ulong(len(buffer))
        if kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            buffer,
            ctypes.byref(tamanho),
        ):
            return Path(buffer.value).name.lower()
    except Exception:
        pass
    finally:
        kernel32.CloseHandle(handle)

    return ""

def _processo_da_janela_windows(hwnd):
    if os.name != "nt" or not hwnd:
        return ""

    user32 = _user32()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    return _nome_executavel_por_pid_windows(pid.value)

def _status_windows():
    if os.name != "nt":
        return None

    kernel32 = ctypes.windll.kernel32

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
    kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
    kernel32.GetTickCount64.argtypes = []
    kernel32.GetTickCount64.restype = ctypes.c_ulonglong

    memoria = MEMORYSTATUSEX()
    memoria.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    memoria_ok = bool(kernel32.GlobalMemoryStatusEx(ctypes.byref(memoria)))

    uptime_ms = int(kernel32.GetTickCount64())
    uptime_total_segundos = max(0, uptime_ms // 1000)
    dias, resto = divmod(uptime_total_segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, segundos = divmod(resto, 60)

    agora = datetime.now().astimezone()

    resultado = {
        "hora": agora.strftime("%H:%M:%S"),
        "data": agora.strftime("%d/%m/%Y"),
        "uptime_segundos": uptime_total_segundos,
        "uptime_formatado": (
            f"{dias}d {horas:02d}h {minutos:02d}min {segundos:02d}s"
        ),
    }

    if memoria_ok:
        total = int(memoria.ullTotalPhys)
        disponivel = int(memoria.ullAvailPhys)
        usado = max(0, total - disponivel)
        resultado.update({
            "ram_percentual": int(memoria.dwMemoryLoad),
            "ram_usada_bytes": usado,
            "ram_total_bytes": total,
            "ram_disponivel_bytes": disponivel,
            "ram_usada_gb": usado / (1024 ** 3),
            "ram_total_gb": total / (1024 ** 3),
        })

    resultado["windows_tick_count_64"] = uptime_ms
    return resultado

def obter_status_windows():
    if os.name != "nt":
        return "Informacoes do sistema estao disponiveis somente no Windows."

    dados = _status_windows()
    if not dados:
        return "Nao consegui obter o estado atual do Windows."

    linhas = [
        f"Hora local: {dados['hora']}",
        f"Data local: {dados['data']}",
    ]

    if "ram_percentual" in dados:
        linhas.append(
            f"RAM: {dados['ram_usada_gb']:.1f} GB de "
            f"{dados['ram_total_gb']:.1f} GB ({dados['ram_percentual']}% usada)"
        )
    else:
        linhas.append("RAM: nao foi possivel obter os dados.")

    linhas.append(f"Tempo ligado: {dados['uptime_formatado']}")
    return "\n".join(linhas)

def _enumerar_janelas_windows(apenas_visiveis=True):
    user32 = _user32()
    if user32 is None:
        return []

    janelas = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    @EnumWindowsProc
    def callback(hwnd, _lparam):
        if apenas_visiveis and not user32.IsWindowVisible(hwnd):
            return True

        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
        titulo = buffer.value.strip()

        if titulo:
            janelas.append((hwnd, titulo))

        return True

    user32.EnumWindows(callback, 0)
    return janelas

def _encontrar_janela_windows_sem_cache(alvo):
    pedido = normalizar_nome(alvo)
    if not pedido:
        return None

    janelas = _enumerar_janelas_windows()
    todas_as_janelas = None

    # O Explorador de Arquivos pode ter como titulo o nome da pasta aberta
    # ("Downloads", "Desktop", etc.), entao o nome do aplicativo sozinho
    # nao aparece necessariamente no titulo da janela.
    aliases_explorer = {
        "gerenciador de arquivos",
        "explorador de arquivos",
        "file explorer",
        "windows explorer",
        "explorer",
    }
    if pedido in aliases_explorer:
        user32 = _user32()
        janela_ativa = user32.GetForegroundWindow() if user32 else 0

        if janela_ativa:
            for hwnd, titulo in janelas:
                if hwnd == janela_ativa and _processo_da_janela_windows(hwnd) == "explorer.exe":
                    return hwnd, titulo

        for hwnd, titulo in janelas:
            if _processo_da_janela_windows(hwnd) == "explorer.exe":
                return hwnd, titulo

    user32 = _user32()
    janela_ativa = user32.GetForegroundWindow() if user32 else 0

    candidatos_exatos = [
        (hwnd, titulo)
        for hwnd, titulo in janelas
        if normalizar_nome(titulo) == pedido
    ]
    for hwnd, titulo in candidatos_exatos:
        if hwnd == janela_ativa:
            return hwnd, titulo
    if candidatos_exatos:
        return candidatos_exatos[0]

    candidatos_parciais = [
        (hwnd, titulo)
        for hwnd, titulo in janelas
        if pedido in normalizar_nome(titulo)
    ]
    for hwnd, titulo in candidatos_parciais:
        if hwnd == janela_ativa:
            return hwnd, titulo
    if candidatos_parciais:
        return candidatos_parciais[0]

    # Quando o titulo visivel nao corresponde ao nome do aplicativo,
    # tenta identificar a janela pelo executavel do processo. Isso cobre
    # casos como Notepad/Bloco de notas no Windows 11, em que o titulo
    # pode ser apenas "Sem titulo" ou "Sem titulo - Bloco de notas".
    # Tambem aceita alvos como "notepad.exe" diretamente.
    candidatos_processo = []
    for hwnd, titulo in janelas:
        processo = _processo_da_janela_windows(hwnd)
        processo_normalizado = normalizar_nome(processo)
        processo_base = normalizar_nome(Path(processo).stem) if processo else ""
        if pedido in {processo_normalizado, processo_base} or (
            processo_base and pedido in processo_base
        ):
            candidatos_processo.append((hwnd, titulo))

    if candidatos_processo:
        user32 = _user32()
        janela_ativa = user32.GetForegroundWindow() if user32 else 0
        for hwnd, titulo in candidatos_processo:
            if hwnd == janela_ativa:
                return hwnd, titulo
        return candidatos_processo[0]

    # Fallback tolerante a erros pequenos de ASR, por exemplo
    # "Gochrome" -> "Google Chrome". So roda depois das correspondencias
    # exata, parcial e por processo, evitando substituir um alvo valido.
    candidatos_fuzzy = []
    for hwnd, titulo in janelas:
        titulo_score = similaridade_nome(pedido, titulo)
        processo = _processo_da_janela_windows(hwnd)
        processo_score = similaridade_nome(pedido, Path(processo).stem if processo else "")
        score = max(titulo_score, processo_score)
        if score >= 0.78:
            candidatos_fuzzy.append((score, hwnd, titulo))

    if candidatos_fuzzy:
        candidatos_fuzzy.sort(key=lambda item: (-item[0], item[1] != janela_ativa))
        _, hwnd, titulo = candidatos_fuzzy[0]
        return hwnd, titulo

    # Janelas minimizadas continuam sendo janelas válidas para controle,
    # embora não apareçam em _enumerar_janelas_windows() por padrão.
    # Só fazemos esta busca ampla depois de esgotar as janelas visíveis,
    # preservando o comportamento atual para títulos duplicados visíveis.
    todas_as_janelas = _enumerar_janelas_windows(apenas_visiveis=False)
    if todas_as_janelas:
        candidatos_exatos = [
            (hwnd, titulo)
            for hwnd, titulo in todas_as_janelas
            if normalizar_nome(titulo) == pedido
        ]
        for hwnd, titulo in candidatos_exatos:
            if hwnd == janela_ativa:
                return hwnd, titulo
        if candidatos_exatos:
            return candidatos_exatos[0]

        candidatos_parciais = [
            (hwnd, titulo)
            for hwnd, titulo in todas_as_janelas
            if pedido in normalizar_nome(titulo)
        ]
        for hwnd, titulo in candidatos_parciais:
            if hwnd == janela_ativa:
                return hwnd, titulo
        if candidatos_parciais:
            return candidatos_parciais[0]

        candidatos_processo = []
        for hwnd, titulo in todas_as_janelas:
            processo = _processo_da_janela_windows(hwnd)
            processo_normalizado = normalizar_nome(processo)
            processo_base = normalizar_nome(Path(processo).stem) if processo else ""
            if pedido in {processo_normalizado, processo_base} or (
                processo_base and pedido in processo_base
            ):
                candidatos_processo.append((hwnd, titulo))

        if candidatos_processo:
            for hwnd, titulo in candidatos_processo:
                if hwnd == janela_ativa:
                    return hwnd, titulo
            return candidatos_processo[0]

    return None

_WINDOW_TARGET_CACHE = {}

def _titulo_atual_da_janela_windows(hwnd):
    if os.name != "nt" or not hwnd:
        return ""
    user32 = _user32()
    if user32 is None:
        return ""
    try:
        tamanho = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, tamanho + 1))
        user32.GetWindowTextW(hwnd, buffer, max(1, tamanho + 1))
        return buffer.value.strip()
    except Exception:
        return ""

def _encontrar_janela_windows(alvo):
    pedido = normalizar_nome(alvo)
    if not pedido:
        return None

    user32 = _user32() if os.name == "nt" else None
    cached = _WINDOW_TARGET_CACHE.get(pedido)
    if cached and user32 is not None:
        hwnd_cache, processo_cache = cached
        try:
            ainda_valida = bool(user32.IsWindow(hwnd_cache))
        except Exception:
            ainda_valida = False
        if ainda_valida:
            processo_atual = _processo_da_janela_windows(hwnd_cache)
            if not processo_cache or processo_atual == processo_cache:
                titulo_atual = _titulo_atual_da_janela_windows(hwnd_cache)
                if titulo_atual:
                    return hwnd_cache, titulo_atual
        _WINDOW_TARGET_CACHE.pop(pedido, None)

    encontrado = _encontrar_janela_windows_sem_cache(alvo)
    if encontrado:
        hwnd, titulo = encontrado
        processo = _processo_da_janela_windows(hwnd)
        _WINDOW_TARGET_CACHE[pedido] = (hwnd, processo)
    return encontrado

def listar_janelas_windows():
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    janelas = _enumerar_janelas_windows()
    if not janelas:
        return "Nenhuma janela visivel com titulo foi encontrada."

    user32 = _user32()
    ativa = user32.GetForegroundWindow() if user32 else 0

    linhas = [f"Janelas visiveis: {len(janelas)}"]
    for indice, (hwnd, titulo) in enumerate(janelas, start=1):
        marcador = " [ATIVA]" if hwnd == ativa else ""
        linhas.append(f"{indice}. {titulo}{marcador}")

    return "\n".join(linhas)

def focar_janela_windows(alvo):
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        if not user32.SetForegroundWindow(hwnd):
            return f"Encontrei '{titulo}', mas o Windows nao permitiu coloca-la em primeiro plano."
        return f"Janela ativada: {titulo}"
    except Exception as erro:
        return f"Nao consegui ativar '{titulo}': {erro}"

def minimizar_janela_windows(alvo):
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_MINIMIZE = 6
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return f"Janela minimizada: {titulo}"
    except Exception as erro:
        return f"Nao consegui minimizar '{titulo}': {erro}"

def maximizar_janela_windows(alvo):
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_MAXIMIZE = 3
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return f"Janela maximizada: {titulo}"
    except Exception as erro:
        return f"Nao consegui maximizar '{titulo}': {erro}"

def _configurar_set_window_pos(user32):
    """Configura assinatura Win64 para SetWindowPos e GetWindowRect."""
    try:
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
    except Exception:
        pass

def _obter_rect_janela_windows(hwnd):
    if os.name != "nt":
        return None
    user32 = _user32()
    _configurar_set_window_pos(user32)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return left, top, right, bottom

def _estado_janela_windows(user32, hwnd):
    try:
        if user32.IsIconic(hwnd):
            return "minimizada"
        if user32.IsZoomed(hwnd):
            return "maximizada"
    except Exception:
        pass
    return "normal"

def obter_geometria_janela_windows(alvo):
    """Retorna posicao, tamanho e estado de uma janela do Windows."""
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()
    rect = _obter_rect_janela_windows(hwnd)
    if rect is None:
        return f"Nao consegui obter a geometria da janela: {titulo}."

    left, top, right, bottom = rect
    largura = max(0, right - left)
    altura = max(0, bottom - top)
    estado = _estado_janela_windows(user32, hwnd)
    return (
        f"Janela: {titulo}\n"
        f"Posicao: x={left}, y={top}\n"
        f"Tamanho: {largura}x{altura}\n"
        f"Estado: {estado}"
    )

def _validar_posicao_janela_windows(x, y):
    user32 = _user32()
    try:
        virtual_x = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
        virtual_y = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
        virtual_w = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
        virtual_h = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
        if virtual_w > 0 and virtual_h > 0:
            if x < virtual_x - 100 or x > virtual_x + virtual_w - 1:
                return False
            if y < virtual_y - 100 or y > virtual_y + virtual_h - 1:
                return False
    except Exception:
        pass
    return True

def mover_janela_windows(alvo, x, y):
    """Move uma janela para uma posicao absoluta da area de trabalho."""
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    try:
        x = int(x)
        y = int(y)
        if not _validar_posicao_janela_windows(x, y):
            return f"Posicao fora da area de trabalho virtual: ({x}, {y})."

        hwnd, titulo = encontrado
        user32 = _user32()
        _configurar_set_window_pos(user32)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        ok = user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        if not ok:
            return f"Nao consegui mover a janela: {titulo}."
        return f"Janela movida: {titulo} para ({x}, {y})."
    except Exception as erro:
        return f"Nao consegui mover '{alvo}': {erro}"

def redimensionar_janela_windows(alvo, largura, altura):
    """Redimensiona uma janela sem alterar sua posicao atual."""
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    try:
        largura = int(largura)
        altura = int(altura)
        if largura < 120 or altura < 80:
            return ToolResult.failure(
                "Tamanho muito pequeno. Use pelo menos 120x80 pixels.",
                error_code="window_size_too_small",
            )
        if largura > 10000 or altura > 10000:
            return ToolResult.failure(
                "Tamanho muito grande. Use no maximo 10000x10000 pixels.",
                error_code="window_size_too_large",
            )

        hwnd, titulo = encontrado
        user32 = _user32()
        _configurar_set_window_pos(user32)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        ok = user32.SetWindowPos(hwnd, 0, 0, 0, largura, altura, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        if not ok:
            return f"Nao consegui redimensionar a janela: {titulo}."
        return f"Janela redimensionada: {titulo} para {largura}x{altura}."
    except Exception as erro:
        return f"Nao consegui redimensionar '{alvo}': {erro}"

def restaurar_janela_windows(alvo):
    """Restaura uma janela minimizada ou maximizada ao estado normal."""
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()
    try:
        if not user32.ShowWindow(hwnd, 9):
            # ShowWindow pode retornar False quando o estado anterior era normal;
            # isso nao significa necessariamente falha.
            pass
        return f"Janela restaurada: {titulo}"
    except Exception as erro:
        return f"Nao consegui restaurar '{titulo}': {erro}"

def fechar_janela_windows(alvo):
    if os.name != "nt":
        return "Controle de janelas do Windows so esta disponivel no Windows."

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return f"Nao encontrei uma janela correspondente a '{alvo}'."

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        WM_CLOSE = 0x0010
        resultado = user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if not resultado:
            return f"Encontrei '{titulo}', mas nao consegui solicitar o fechamento."
        return f"Solicitei o fechamento da janela: {titulo}"
    except Exception as erro:
        return f"Nao consegui fechar '{titulo}': {erro}"

_UI_AUTOMATION_POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Normalize-Text([string]$Text) {
    if ($null -eq $Text) { return '' }
    try {
        $formD = $Text.Normalize([System.Text.NormalizationForm]::FormD)
        $semAcentos = [System.Text.RegularExpressions.Regex]::Replace($formD, '\p{Mn}', '')
        return [System.Text.RegularExpressions.Regex]::Replace($semAcentos.ToLowerInvariant(), '[^\p{L}\p{N}]+', ' ').Trim()
    } catch {
        return ($Text.ToLowerInvariant()).Trim()
    }
}

function Safe-String($Value) {
    if ($null -eq $Value) { return '' }
    try { return [string]$Value } catch { return '' }
}

function Get-ControlTypeName($Element) {
    try {
        $programmatic = Safe-String($Element.Current.ControlType.ProgrammaticName)
        if ($programmatic -match '\.([^\.]+)$') { return $Matches[1] }
        return $programmatic
    } catch { return '' }
}

function Get-PatternNames($Element) {
    # Mantemos a inspeção inicial enxuta. Padrões caros como TextPattern/Scroll
    # não são necessários para localizar os controles básicos e podem provocar
    # chamadas lentas em alguns provedores de UI. Eles ficam fora do inventário
    # inicial e podem ser adicionados futuramente em operações específicas.
    $patterns = [System.Collections.Generic.List[string]]::new()
    $known = @(
        @('Invoke', [System.Windows.Automation.InvokePattern]::Pattern),
        @('Value', [System.Windows.Automation.ValuePattern]::Pattern),
        @('Toggle', [System.Windows.Automation.TogglePattern]::Pattern),
        @('SelectionItem', [System.Windows.Automation.SelectionItemPattern]::Pattern),
        @('ExpandCollapse', [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    )
    foreach ($item in $known) {
        try {
            $null = $Element.GetCurrentPattern($item[1])
            $patterns.Add([string]$item[0])
        } catch {}
    }
    return $patterns.ToArray()
}

function Get-PatternState($Element, $PatternNames) {
    $states = New-Object System.Collections.Generic.List[string]
    if ($PatternNames -contains 'Toggle') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            $states.Add('toggle=' + (Safe-String $pattern.Current.ToggleState))
        } catch {}
    }
    if ($PatternNames -contains 'SelectionItem') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $states.Add('selected=' + ([bool]$pattern.Current.IsSelected))
        } catch {}
    }
    if ($PatternNames -contains 'ExpandCollapse') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            $states.Add('expand=' + (Safe-String $pattern.Current.ExpandCollapseState))
        } catch {}
    }
    return ($states -join '; ')
}

function Get-ElementText($Element, $ControlType, $PatternNames, [bool]$IsPassword) {
    if ($IsPassword) { return '' }

    # Para controles de edição, ValuePattern é a fonte de texto confiável.
    # Evitamos TextPattern durante a enumeração geral para não forçar provedores
    # mais pesados em toda a árvore.
    if ($PatternNames -contains 'Value') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $value = Safe-String $pattern.Current.Value
            if ($value) { return $value }
        } catch {}
    }

    # O Name de Text/Status/Buttons normalmente já expõe o texto útil pela UIA.
    if ($ControlType -in @('Text', 'Button', 'CheckBox', 'ListItem', 'MenuItem', 'TabItem')) {
        try {
            $name = Safe-String $Element.Current.Name
            if ($name) { return $name }
        } catch {}
    }
    return ''
}

function Get-ElementInfo($Element) {
    try { $name = Safe-String $Element.Current.Name } catch { $name = '' }
    try { $automationId = Safe-String $Element.Current.AutomationId } catch { $automationId = '' }
    try { $className = Safe-String $Element.Current.ClassName } catch { $className = '' }
    try { $helpText = Safe-String $Element.Current.HelpText } catch { $helpText = '' }
    try { $enabled = [bool]$Element.Current.IsEnabled } catch { $enabled = $false }
    try { $offscreen = [bool]$Element.Current.IsOffscreen } catch { $offscreen = $false }
    try { $isPassword = [bool]$Element.Current.IsPassword } catch { $isPassword = $false }
    $controlType = Get-ControlTypeName $Element
    $patterns = Get-PatternNames $Element
    $text = Get-ElementText $Element $controlType $patterns $isPassword
    $state = Get-PatternState $Element $patterns
    [pscustomobject]@{
        Element = $Element
        Name = $name
        AutomationId = $automationId
        ClassName = $className
        HelpText = $helpText
        ControlType = $controlType
        Enabled = $enabled
        Offscreen = $offscreen
        IsPassword = $isPassword
        Patterns = @($patterns)
        Text = $text
        State = $state
    }
}

function Get-RootElement($Hwnd) {
    $handle = [IntPtr]::new([int64]$Hwnd)
    if ($handle -eq [IntPtr]::Zero) { throw 'Handle de janela invalido.' }
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
    if ($null -eq $root) { throw 'Nao consegui acessar a janela pela UI Automation.' }
    return $root
}

function Get-AllControls($Root) {
    # Em vez de uma única busca profunda, percorremos a árvore em BFS usando
    # apenas Children. Isso evita prender o processo em um provedor de UI ruim
    # e mantém um limite total para interfaces enormes.
    $fila = [System.Collections.Generic.Queue[object]]::new()
    $fila.Enqueue([pscustomobject]@{ Element = $Root; Depth = 0 })
    $items = [System.Collections.Generic.List[object]]::new()
    $visitados = 0
    $maxVisitados = 300
    $maxProfundidade = 14

    while ($fila.Count -gt 0 -and $visitados -lt $maxVisitados) {
        $entrada = $fila.Dequeue()
        $element = $entrada.Element
        $profundidade = [int]$entrada.Depth

        if ($null -eq $element) { continue }
        $visitados++

        try {
            $item = Get-ElementInfo $element
            $isControl = $false
            try { $isControl = [bool]$element.Current.IsControlElement } catch {}
            if ($isControl -and -not $item.Offscreen) {
                if ($item.Name -or $item.AutomationId -or $item.Text -or $item.IsPassword -or ($item.ControlType -in @('Button','Edit','Document','CheckBox','ComboBox','ListItem','MenuItem','TabItem','Text','List','Window'))) {
                    $items.Add($item)
                }
            }
        } catch {}

        if ($profundidade -ge $maxProfundidade) { continue }

        try {
            $children = $element.FindAll(
                [System.Windows.Automation.TreeScope]::Children,
                [System.Windows.Automation.Condition]::TrueCondition
            )
            for ($i = 0; $i -lt $children.Count; $i++) {
                if ($visitados + $fila.Count -ge $maxVisitados) { break }
                $filho = $children.Item($i)
                if ($null -ne $filho) { $fila.Enqueue([pscustomobject]@{ Element = $filho; Depth = ($profundidade + 1) }) }
            }
        } catch {}
    }

    return $items.ToArray()
}

function Get-MatchQuery([string]$Raw) {
    $norm = Normalize-Text $Raw
    $typeHint = ''
    $typeWords = @{
        'botao'='Button'; 'button'='Button';
        'campo'='Edit'; 'edit'='Edit'; 'textbox'='Edit';
        'checkbox'='CheckBox'; 'check'='CheckBox';
        'lista'='List'; 'list'='List';
        'item'='ListItem';
        'menu'='MenuItem'; 'menuitem'='MenuItem';
        'aba'='TabItem'; 'tab'='TabItem';
        'combo'='ComboBox'; 'combobox'='ComboBox'
    }
    $tokens = @($norm -split '\s+' | Where-Object { $_ })
    $kept = New-Object System.Collections.Generic.List[string]
    $keptLoose = New-Object System.Collections.Generic.List[string]
    foreach ($token in $tokens) {
        if ($typeWords.ContainsKey($token)) {
            $typeHint = $typeWords[$token]
            continue
        }
        $kept.Add($token)
        if ($token -notin @('de','do','da','dos','das','o','a','os','as','em','no','na','nos','nas')) {
            $keptLoose.Add($token)
        }
    }
    [pscustomobject]@{
        FullQuery = $norm
        RawQuery = (($kept -join ' ').Trim())
        LooseQuery = (($keptLoose -join ' ').Trim())
        TypeHint = $typeHint
    }
}

function Find-Controls($Items, [string]$Target, [string]$PreferPattern = '') {
    $query = Get-MatchQuery $Target
    $matches = [System.Collections.Generic.List[object]]::new()
    foreach ($item in $Items) {
        $name = Normalize-Text $item.Name
        $automationId = Normalize-Text $item.AutomationId
        $help = Normalize-Text $item.HelpText
        $text = Normalize-Text $item.Text
        $fullQuery = $query.FullQuery
        $rawQuery = $query.RawQuery
        $looseQuery = $query.LooseQuery
        $score = -1

        # Primeiro considera o pedido completo, antes de remover palavras de tipo.
        # Assim "Campo de Teste" nao empata com "Senha de Teste".
        if ($fullQuery) {
            if ($name -eq $fullQuery) { $score = 120 }
            elseif ($automationId -eq $fullQuery) { $score = 115 }
            elseif ($name.Contains($fullQuery)) { $score = 100 }
            elseif ($automationId.Contains($fullQuery)) { $score = 95 }
            elseif ($help.Contains($fullQuery) -or $text.Contains($fullQuery)) { $score = 85 }
        }

        if ($rawQuery) {
            if ($name -eq $rawQuery) { $score = [Math]::Max($score, 105) }
            elseif ($automationId -eq $rawQuery) { $score = [Math]::Max($score, 100) }
            elseif ($name.Contains($rawQuery)) { $score = [Math]::Max($score, 85) }
            elseif ($automationId.Contains($rawQuery)) { $score = [Math]::Max($score, 80) }
            elseif ($help.Contains($rawQuery) -or $text.Contains($rawQuery)) { $score = [Math]::Max($score, 70) }
        }

        if ($looseQuery) {
            $nameTokens = @($name -split '\s+' | Where-Object { $_ })
            $looseTokens = @($looseQuery -split '\s+' | Where-Object { $_ })
            $tokensPresent = $true
            foreach ($token in $looseTokens) {
                if ($token -notin $nameTokens -and $token -notin @($automationId -split '\s+')) {
                    $tokensPresent = $false
                    break
                }
            }
            if ($tokensPresent -and $looseTokens.Count -gt 0) {
                $score = [Math]::Max($score, 72)
            }
            elseif ($score -lt 0 -and ($name.Contains($looseQuery) -or $automationId.Contains($looseQuery) -or $help.Contains($looseQuery) -or $text.Contains($looseQuery))) {
                $score = 60
            }
        }

        if ($query.TypeHint) {
            if ($item.ControlType -ne $query.TypeHint) {
                if ($score -ge 0) { $score -= 30 } else { $score = -1 }
            }
            elseif ($score -lt 0 -and -not $query.RawQuery -and -not $query.LooseQuery) {
                $score = 50
            }
        }

        if ($score -ge 0 -and $PreferPattern) {
            if ($item.Patterns -contains $PreferPattern) {
                $score += 25
            }
        }

        if ($score -ge 0) { $matches.Add([pscustomobject]@{ Score=$score; Item=$item }) }
    }
    return @($matches | Sort-Object -Property @{Expression='Score';Descending=$true})
}

function Format-Item($Item, [int]$Index) {
    $name = if ($Item.Name) { $Item.Name } else { '[sem nome]' }
    $id = if ($Item.AutomationId) { $Item.AutomationId } else { '[sem AutomationId]' }
    $text = if ($Item.Text) { $Item.Text -replace '\r?\n',' ' } else { '' }
    if ($text.Length -gt 240) { $text = $text.Substring(0,240) + '...' }
    $valor = ''
    # Campos de senha nunca tem o valor lido/exibido. Controles editaveis
    # comuns que oferecem ValuePattern podem reportar o valor atual para que
    # a inspecao consiga confirmar mudancas reais de estado.
    if (-not $Item.IsPassword -and ($Item.Patterns -contains 'Value')) {
        try {
            $valuePattern = $Item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $valor = Safe-String $valuePattern.Current.Value
        } catch {}
    }
    [pscustomobject]@{
        indice = $Index
        nome = $name
        automation_id = $id
        classe = $Item.ClassName
        tipo = $Item.ControlType
        habilitado = $Item.Enabled
        protegido = $Item.IsPassword
        padroes = @($Item.Patterns)
        estado = $Item.State
        texto = $text
        valor = $valor
    }
}

try {
    $payload = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
    $outputPath = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__OUTPUT_FILE_B64__'))
    $root = Get-RootElement ([string]$payload.hwnd)
    $items = Get-AllControls $root

    if ($payload.operacao -eq 'inspecionar') {
        $foco = [string]$payload.foco
        $max = [int]$payload.max_itens
        if ($max -lt 1) { $max = 1 }
        if ($max -gt 80) { $max = 80 }
        if ([string]::IsNullOrWhiteSpace($foco)) {
            $selecionados = @($items | Select-Object -First $max)
        } else {
            $matches = Find-Controls $items $foco
            $selecionados = @($matches | Select-Object -First $max | ForEach-Object { $_.Item })
        }
        $saida = @()
        $i = 1
        foreach ($item in $selecionados) { $saida += Format-Item $item $i; $i++ }
        $resultado = [pscustomobject]@{ ok=$true; operacao='inspecionar'; controles=@($saida); total=[int]$items.Count }
    } else {
        $target = [string]$payload.alvo
        if ([string]::IsNullOrWhiteSpace($target)) { throw 'Informe o nome, texto, AutomationId ou tipo do controle.' }
        $preferPattern = ''
        if ($payload.operacao -eq 'preencher') { $preferPattern = 'Value' }
        elseif ($payload.operacao -eq 'alternar') { $preferPattern = 'Toggle' }
        elseif ($payload.operacao -eq 'selecionar') { $preferPattern = 'SelectionItem' }
        elseif ($payload.operacao -eq 'clicar') { $preferPattern = 'Invoke' }
        $matches = Find-Controls $items $target $preferPattern
        if ($matches.Count -eq 0) { throw "Nao encontrei um controle correspondente a '$target'." }
        $indice = [int]$payload.indice
        if ($indice -lt 1 -or $indice -gt $matches.Count) { throw "Indice invalido para '$target'. Encontrei $($matches.Count) controle(s)." }

        if ($indice -eq 1 -and $matches.Count -gt 1) {
            $topScore = [int]$matches[0].Score
            $secondScore = [int]$matches[1].Score
            if ($topScore -eq $secondScore) {
                $candidatos = @($matches | Select-Object -First 5 | ForEach-Object {
                    $id = if ($_.Item.AutomationId) { $_.Item.AutomationId } else { '[sem AutomationId]' }
                    "$($_.Item.Name) [$($_.Item.ControlType); id=$id; protegido=$($_.Item.IsPassword); score=$($_.Score)]"
                })
                throw "Alvo ambiguo para '$target'. Dois ou mais controles empataram: $($candidatos -join ' | ')"
            }
        }

        $item = $matches[$indice - 1].Item
        if (-not $item.Enabled) { throw "O controle '$($item.Name)' esta desabilitado." }
        if ($item.Offscreen) { throw "O controle '$($item.Name)' esta fora da area visivel." }

        if ($payload.operacao -eq 'resolver') {
            $resultado = [pscustomobject]@{
                ok=$true; operacao='resolver'; nome=$item.Name; automation_id=$item.AutomationId;
                tipo=$item.ControlType; protegido=$item.IsPassword; score=[int]$matches[$indice - 1].Score;
                resultado="Controle resolvido: '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword)."
            }
        } elseif ($payload.operacao -eq 'clicar') {
            if ($item.Patterns -contains 'Invoke') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $pattern.Invoke()
            } elseif ($item.Patterns -contains 'ExpandCollapse') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
                if ((Safe-String $pattern.Current.ExpandCollapseState) -eq 'Collapsed') { $pattern.Expand() } else { $pattern.Collapse() }
            } elseif ($item.Patterns -contains 'SelectionItem') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
                $pattern.Select()
            } else {
                throw "O controle '$($item.Name)' nao oferece um padrao acionavel pela UI Automation."
            }
            Start-Sleep -Milliseconds 120
            $resultado = [pscustomobject]@{ ok=$true; operacao='clicar'; nome=$item.Name; tipo=$item.ControlType; resultado="Clique executado em '$($item.Name)' ($($item.ControlType))." }
        } elseif ($payload.operacao -eq 'preencher') {
            if ($item.IsPassword -and -not [bool]$payload.permitir_protegido) {
                throw "O controle '$($item.Name)' e protegido por IsPassword. O preenchimento de campos protegidos exige confirmacao explicita."
            }
            if (-not [bool]$item.IsPassword -and -not ($item.Patterns -contains 'Value')) {
                throw "O controle '$($item.Name)' nao oferece ValuePattern para preenchimento."
            }
            $textoDesejado = [string]$payload.texto
            $valuePattern = $null
            if (-not [bool]$item.IsPassword) {
                $valuePattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ([bool]$valuePattern.Current.IsReadOnly) { throw "O controle '$($item.Name)' e somente leitura." }
            }

            # O fluxo recomendado para entrada via UI Automation e dar foco
            # primeiro e depois usar ValuePattern.SetValue(). Alguns provedores
            # WPF falham ou permanecem com valor antigo quando SetValue e chamado
            # sem o foco do controle.
            try { $item.Element.SetFocus() } catch {}
            Start-Sleep -Milliseconds 100
            $setValueExecutado = $false
            $confirmado = ''

            # Campos protegidos (PasswordBox/IsPassword) nao usam SetValue como
            # evidencia de execucao. Alguns provedores podem aceitar SetValue sem
            # disparar os eventos normais do controle; nesses casos a entrada
            # fisica e a unica forma de preservar o comportamento real da interface.
            if (-not [bool]$item.IsPassword) {
                try {
                    $valuePattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                    $valuePattern.SetValue($textoDesejado)
                    $setValueExecutado = $true
                } catch {}
                Start-Sleep -Milliseconds 180

                # Releia o controle a partir da arvore atual para evitar depender de
                # um AutomationElement/pattern que possa estar com estado desatualizado.
                try {
                    $freshRoot = Get-RootElement ([string]$payload.hwnd)
                    $freshItems = Get-AllControls $freshRoot
                    $freshMatches = Find-Controls $freshItems $target 'Value'
                    if ($freshMatches.Count -gt 0) {
                        $freshItem = $freshMatches[0].Item
                        $freshPattern = $freshItem.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                        $confirmado = Safe-String $freshPattern.Current.Value
                        $item = $freshItem
                        $valuePattern = $freshPattern
                    }
                } catch {
                    try { $confirmado = Safe-String $valuePattern.Current.Value } catch { $confirmado = '' }
                }
            }

            # Fallback para provedores que anunciam ValuePattern, mas nao
            # efetivam SetValue de forma confiavel. Para controles protegidos,
            # a entrada usa eventos de teclado reais via SendInput, mapeando
            # caracteres para teclas virtuais quando possivel e usando Unicode
            # apenas como fallback. Isso preserva KeyDown/WM_CHAR em WPF em vez
            # de depender exclusivamente de VK_PACKET.
            if ($item.IsPassword -or $confirmado -ne $textoDesejado) {
                try {
                    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class AurenUiWin32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [DllImport("user32.dll", SetLastError=true)] private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [DllImport("user32.dll")] private static extern short VkKeyScanEx(char ch, IntPtr dwhkl);
    [DllImport("user32.dll")] private static extern IntPtr GetKeyboardLayout(uint idThread);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr lpdwProcessId);
    [DllImport("user32.dll")] private static extern uint MapVirtualKeyEx(uint uCode, uint uMapType, IntPtr dwhkl);

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;
    private const uint KEYEVENTF_SCANCODE = 0x0008;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    private const uint MAPVK_VK_TO_VSC_EX = 4;
    private const ushort VK_SHIFT = 0x10;
    private const ushort VK_CONTROL = 0x11;
    private const ushort VK_MENU = 0x12;
    private const ushort VK_A = 0x41;
    private const ushort VK_BACK = 0x08;

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT {
        public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT {
        public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct HARDWAREINPUT {
        public uint uMsg; public ushort wParamL; public ushort wParamH;
    }

    private static INPUT Key(ushort vk, uint flags) {
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = vk, wScan = 0, dwFlags = flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static INPUT Unicode(char ch, uint flags) {
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = ch, dwFlags = KEYEVENTF_UNICODE | flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static INPUT ScanKey(ushort vk, bool keyUp, IntPtr layout) {
        uint scanEx = MapVirtualKeyEx(vk, MAPVK_VK_TO_VSC_EX, layout);
        ushort scan = (ushort)(scanEx & 0xFF);
        uint flags = KEYEVENTF_SCANCODE | (keyUp ? KEYEVENTF_KEYUP : 0);
        if ((scanEx & 0xE000) != 0) flags |= KEYEVENTF_EXTENDEDKEY;
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = scan, dwFlags = flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static int AddMappedChar(List<INPUT> inputs, char ch, IntPtr layout) {
        short mapped = VkKeyScanEx(ch, layout);
        if (mapped == -1) {
            inputs.Add(Unicode(ch, 0));
            inputs.Add(Unicode(ch, KEYEVENTF_KEYUP));
            return 2;
        }

        ushort vk = (ushort)(mapped & 0x00FF);
        byte shiftState = (byte)((mapped >> 8) & 0xFF);
        var mods = new List<ushort>();
        if ((shiftState & 1) != 0) mods.Add(VK_SHIFT);
        if ((shiftState & 2) != 0) mods.Add(VK_CONTROL);
        if ((shiftState & 4) != 0) mods.Add(VK_MENU);

        foreach (ushort mod in mods) inputs.Add(ScanKey(mod, false, layout));
        inputs.Add(ScanKey(vk, false, layout));
        inputs.Add(ScanKey(vk, true, layout));
        for (int i = mods.Count - 1; i >= 0; i--) inputs.Add(ScanKey(mods[i], true, layout));
        return 2 + (2 * mods.Count);
    }

    private static uint SendBatch(List<INPUT> inputs) {
        if (inputs.Count == 0) return 0;
        return SendInput((uint)inputs.Count, inputs.ToArray(), Marshal.SizeOf(typeof(INPUT)));
    }

    public static uint SendText(string text, IntPtr hwnd) {
        uint total = 0;
        IntPtr layout = GetKeyboardLayout(GetWindowThreadProcessId(hwnd, IntPtr.Zero));

        // Limpa o valor atual sem usar ValuePattern. Cada etapa e enviada como
        // uma pequena sequencia e damos tempo para a fila de entrada do WPF
        // processar os eventos antes de continuar.
        var clear = new List<INPUT>();
        clear.Add(ScanKey(VK_CONTROL, false, layout));
        clear.Add(ScanKey(VK_A, false, layout));
        clear.Add(ScanKey(VK_A, true, layout));
        clear.Add(ScanKey(VK_CONTROL, true, layout));
        clear.Add(ScanKey(VK_BACK, false, layout));
        clear.Add(ScanKey(VK_BACK, true, layout));
        total += SendBatch(clear);
        System.Threading.Thread.Sleep(35);

        foreach (char ch in text) {
            var one = new List<INPUT>();
            AddMappedChar(one, ch, layout);
            uint accepted = SendBatch(one);
            total += accepted;
            System.Threading.Thread.Sleep(18);
        }
        return total;
    }

    public static int CountTextInputs(string text) {
        var probe = new List<INPUT>();
        IntPtr layout = GetKeyboardLayout(0);
        probe.Add(ScanKey(VK_CONTROL, false, layout));
        probe.Add(ScanKey(VK_A, false, layout));
        probe.Add(ScanKey(VK_A, true, layout));
        probe.Add(ScanKey(VK_CONTROL, true, layout));
        probe.Add(ScanKey(VK_BACK, false, layout));
        probe.Add(ScanKey(VK_BACK, true, layout));
        foreach (char ch in text) AddMappedChar(probe, ch, layout);
        return probe.Count;
    }
}
'@
                } catch {}
                $foregroundSeguro = $false
                $controleFocado = $false
                $fallbackExecutado = $false
                $physicalClickConfirmed = $false
                try {
                    $hwndInt = [Int64]$payload.hwnd
                    for ($tentativa = 0; $tentativa -lt 5 -and -not $foregroundSeguro; $tentativa++) {
                        [AurenUiWin32]::ShowWindow([IntPtr]$hwndInt, 9) | Out-Null
                        [AurenUiWin32]::SetForegroundWindow([IntPtr]$hwndInt) | Out-Null
                        Start-Sleep -Milliseconds (80 + ($tentativa * 60))
                        $foregroundAtual = [AurenUiWin32]::GetForegroundWindow()
                        $foregroundSeguro = ($foregroundAtual -eq [IntPtr]$hwndInt)
                    }
                } catch {}

                if ($foregroundSeguro) {
                    # PasswordBox nao expoe ValuePattern de forma segura. Antes de
                    # qualquer entrada de teclado, o controle protegido precisa receber foco
                    # tanto pela UI Automation quanto por uma interacao fisica real.
                    try {
                        $ponto = $item.Element.GetClickablePoint()
                        if ([AurenUiWin32]::SetCursorPos([int]$ponto.X, [int]$ponto.Y)) {
                            [AurenUiWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
                            Start-Sleep -Milliseconds 35
                            [AurenUiWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
                            $physicalClickConfirmed = $true
                        }
                    } catch {}

                    try { $item.Element.SetFocus() } catch {}
                    Start-Sleep -Milliseconds 140
                    try {
                        $focoAtual = [System.Windows.Automation.AutomationElement]::FocusedElement
                        if ($focoAtual) {
                            $focoNome = Safe-String $focoAtual.Current.Name
                            $focoId = Safe-String $focoAtual.Current.AutomationId
                            $controleFocado = (
                                ($focoId -and $item.AutomationId -and ($focoId -eq $item.AutomationId)) -or
                                ($focoNome -and $item.Name -and ($focoNome -eq $item.Name))
                            )
                        }
                    } catch {}

                    # A entrada fisica so pode ocorrer quando o HWND continua em
                    # primeiro plano, o clique fisico ocorreu e o controle exato
                    # foi confirmado como foco atual.
                    if ($controleFocado) {
                        try {
                            $foregroundAtual = [AurenUiWin32]::GetForegroundWindow()
                            $foregroundSeguro = ($foregroundAtual -eq [IntPtr]$hwndInt)
                        } catch {
                            $foregroundSeguro = $false
                        }
                    }

                    if ($foregroundSeguro -and $physicalClickConfirmed -and $controleFocado) {
                        try {
                            $inputCount = [AurenUiWin32]::SendText([string]$textoDesejado, [IntPtr]$hwndInt)
                            $esperado = [AurenUiWin32]::CountTextInputs([string]$textoDesejado)
                            $fallbackExecutado = ($inputCount -eq [uint32]$esperado)
                            Start-Sleep -Milliseconds 350
                        } catch {}
                    }
                }

                # Confirma novamente por um AutomationElement completamente novo.
                try {
                    $freshRoot = Get-RootElement ([string]$payload.hwnd)
                    $freshItems = Get-AllControls $freshRoot
                    $freshMatches = Find-Controls $freshItems $target 'Value'
                    if ($freshMatches.Count -gt 0) {
                        $freshItem = $freshMatches[0].Item
                        $freshPattern = $freshItem.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                        $confirmado = Safe-String $freshPattern.Current.Value
                    }
                } catch {}
            }

            $confirmadoBool = ($confirmado -eq $textoDesejado)
            $confirmadoProtegidoSemLeitura = (
                [bool]$item.IsPassword -and
                $foregroundSeguro -and
                $physicalClickConfirmed -and
                $fallbackExecutado -and
                $controleFocado
            )
            if ($confirmadoProtegidoSemLeitura) {
                $confirmadoBool = $true
            }
            $resultado = [pscustomobject]@{
                ok=$true
                operacao='preencher'
                nome=$item.Name
                tipo=$item.ControlType
                automation_id=$item.AutomationId
                protegido=$item.IsPassword
                confirmado=$confirmadoBool
                entrada_fisica_executada=$fallbackExecutado
                controle_focado=$controleFocado
                clique_fisico_confirmado=$physicalClickConfirmed
                entrada_fisica_eventos_enviados=$(if ($item.IsPassword) { $inputCount } else { 0 })
                entrada_fisica_eventos_esperados=$(if ($item.IsPassword) { $esperado } else { 0 })
                entrada_fisica_ok=$fallbackExecutado
                resultado=$(if ($confirmadoProtegidoSemLeitura) {
                    "Preenchimento executado em controle protegido '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=True. O valor nao e legivel pela UI Automation."
                } elseif ($confirmadoBool) {
                    "Preenchimento concluido em '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword)."
                } else {
                    "Preenchimento nao confirmado em '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword); fallback_foreground_confirmado=$foregroundSeguro; controle_focado=$controleFocado."
                })
            }
        } elseif ($payload.operacao -eq 'alternar') {
            if (-not ($item.Patterns -contains 'Toggle')) { throw "O controle '$($item.Name)' nao oferece TogglePattern." }
            $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            $pattern.Toggle()
            Start-Sleep -Milliseconds 120
            $estado = Safe-String $pattern.Current.ToggleState
            $resultado = [pscustomobject]@{ ok=$true; operacao='alternar'; nome=$item.Name; tipo=$item.ControlType; estado=$estado; resultado="Estado alternado de '$($item.Name)': $estado." }
        } elseif ($payload.operacao -eq 'selecionar') {
            if (-not ($item.Patterns -contains 'SelectionItem')) { throw "O controle '$($item.Name)' nao oferece SelectionItemPattern." }
            $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $pattern.Select()
            Start-Sleep -Milliseconds 120
            $selecionado = [bool]$pattern.Current.IsSelected
            $resultado = [pscustomobject]@{ ok=$true; operacao='selecionar'; nome=$item.Name; tipo=$item.ControlType; selecionado=$selecionado; resultado="Elemento selecionado: '$($item.Name)'." }
        } else {
            throw "Operacao UI Automation desconhecida: $($payload.operacao)"
        }
    }
    $json = $resultado | ConvertTo-Json -Compress -Depth 7
    [System.IO.File]::WriteAllText($outputPath, [string]$json, (New-Object System.Text.UTF8Encoding($false)))
} catch {
    $erroJson = [pscustomobject]@{ ok=$false; erro=(Safe-String $_.Exception.Message); tipo=(Safe-String $_.Exception.GetType().FullName) } | ConvertTo-Json -Compress -Depth 5
    try { [System.IO.File]::WriteAllText($outputPath, [string]$erroJson, (New-Object System.Text.UTF8Encoding($false))) } catch {}
    Write-Error $_
    exit 1
}
"""

def _ui_automation_hwnd_int(hwnd):
    """Converte HWND para inteiro de forma segura em diferentes versoes do ctypes."""
    valor = getattr(hwnd, "value", hwnd)
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0

def _ui_automation_janela(alvo):
    """Resolve a janela alvo e retorna (hwnd, titulo, erro)."""
    if os.name != "nt":
        return None, None, "Automacao de interface do Windows so esta disponivel no Windows."
    user32 = _user32()
    if user32 is None:
        return None, None, "Nao consegui acessar a API de janelas do Windows."
    pedido = str(alvo or "").strip()
    if pedido:
        encontrado = _encontrar_janela_windows(pedido)
        if not encontrado:
            return None, None, f"Nao encontrei uma janela correspondente a '{pedido}'."
        return encontrado[0], encontrado[1], None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None, "Nao encontrei uma janela em primeiro plano."
    tamanho = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, tamanho + 1))
    user32.GetWindowTextW(hwnd, buffer, max(1, tamanho + 1))
    titulo = buffer.value.strip() or f"HWND {_ui_automation_hwnd_int(hwnd)}"
    return hwnd, titulo, None

def _executar_ui_automation(operacao, dados):
    """Executa uma operacao UI Automation atraves das APIs nativas do Windows."""
    payload = {"operacao": operacao, **(dados or {})}
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return {"ok": False, "erro": "Windows PowerShell nao foi encontrado."}

    encoded_payload = base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    output_path = None
    script_path = None
    try:
        output_path = tempfile.NamedTemporaryFile(
            mode="wb",
            suffix="_auren_uia.json",
            delete=False,
        ).name
        encoded_output_path = base64.b64encode(
            output_path.encode("utf-8")
        ).decode("ascii")
        script = _UI_AUTOMATION_POWERSHELL.replace("__PAYLOAD__", encoded_payload)
        script = script.replace("__OUTPUT_FILE_B64__", encoded_output_path)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            suffix="_auren_uia.ps1",
            delete=False,
        ) as arquivo:
            arquivo.write(script)
            script_path = arquivo.name

        processo = subprocess.run(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-STA",
                "-File",
                script_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "erro": "A operacao de UI Automation excedeu o limite de 20 segundos."}
    except Exception as erro:
        return {"ok": False, "erro": f"Falha ao iniciar o Windows PowerShell: {erro}"}
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    try:
        if output_path and os.path.exists(output_path):
            try:
                saida = Path(output_path).read_text(encoding="utf-8-sig", errors="replace").strip()
            except OSError as erro:
                saida = ""
                leitura_erro = str(erro)
            else:
                leitura_erro = ""
        else:
            saida = ""
            leitura_erro = "arquivo de saida nao criado"
    finally:
        if output_path:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    if not saida:
        stderr = processo.stderr.strip()
        codigo = processo.returncode
        detalhes = stderr[:1600] if stderr else leitura_erro
        if detalhes:
            return {"ok": False, "erro": f"Windows PowerShell saiu com codigo {codigo}: {detalhes}"}
        return {"ok": False, "erro": f"UI Automation nao retornou resultado (PowerShell codigo {codigo}; saida em arquivo ausente/vazia)."}

    try:
        resultado = json.loads(saida)
    except json.JSONDecodeError:
        stderr = processo.stderr.strip()
        return {"ok": False, "erro": stderr[:1600] if stderr else f"Resposta invalida da UI Automation (PowerShell codigo {processo.returncode}): {saida[:800]}"}
    if not isinstance(resultado, dict):
        return {"ok": False, "erro": "UI Automation retornou uma estrutura inesperada."}
    return resultado

def inspecionar_interface_windows(alvo_janela="", foco="", max_itens=40):
    """Inspeciona controles visiveis da janela usando UI Automation."""
    hwnd, titulo, erro = _ui_automation_janela(alvo_janela)
    if erro:
        return erro
    try:
        max_itens = max(1, min(80, int(max_itens)))
    except (TypeError, ValueError):
        return "Quantidade maxima de itens invalida."
    resultado = _executar_ui_automation("inspecionar", {"hwnd": _ui_automation_hwnd_int(hwnd), "foco": str(foco or ""), "max_itens": max_itens})
    if not resultado.get("ok"):
        return f"Nao consegui inspecionar a interface de '{titulo}': {resultado.get('erro', 'erro desconhecido')}"
    controles = resultado.get("controles") or []
    linhas = [
        f"Janela: {titulo}",
        f"Controles encontrados na arvore: {resultado.get('total', 0)}",
        f"Controles exibidos: {len(controles)}",
    ]
    for controle in controles:
        nome = controle.get("nome") or "[sem nome]"
        tipo = controle.get("tipo") or "[sem tipo]"
        automation_id = controle.get("automation_id") or "[sem AutomationId]"
        padroes = ", ".join(controle.get("padroes") or []) or "nenhum"
        linha = f"{controle.get('indice','?')}. {nome} | tipo={tipo} | id={automation_id} | habilitado={controle.get('habilitado')} | protegido={controle.get('protegido')} | padroes={padroes}"
        if controle.get("estado"):
            linha += f" | estado={controle['estado']}"
        if controle.get("texto"):
            linha += f" | texto={str(controle['texto'])[:240]}"
        linhas.append(linha)
    if foco and not controles:
        linhas.append(f"Nenhum controle correspondeu a '{foco}'.")
    return "\n".join(linhas)

def _executar_acao_ui_windows(operacao, alvo_janela, alvo, indice, texto=None, permitir_protegido=False):
    hwnd, titulo, erro = _ui_automation_janela(alvo_janela)
    if erro:
        return erro
    try:
        indice = int(indice)
        if indice < 1:
            return "O indice do elemento deve comecar em 1."
    except (TypeError, ValueError):
        return "Indice de elemento invalido."
    dados = {"hwnd": _ui_automation_hwnd_int(hwnd), "alvo": str(alvo or ""), "indice": indice}
    if texto is not None:
        dados["texto"] = str(texto)
    if operacao == "preencher":
        dados["permitir_protegido"] = bool(permitir_protegido)
    resultado = _executar_ui_automation(operacao, dados)
    if not resultado.get("ok"):
        verbos = {"clicar": "clicar", "preencher": "preencher", "alternar": "alternar", "selecionar": "selecionar"}
        return f"Nao consegui {verbos.get(operacao, operacao)} '{alvo}' na janela '{titulo}': {resultado.get('erro', 'erro desconhecido')}"
    if operacao == "preencher" and resultado.get("confirmado") is False:
        nome_real = resultado.get("nome") or alvo
        automation_id = resultado.get("automation_id") or "[sem AutomationId]"
        protegido = resultado.get("protegido")
        return (f"Preenchimento nao confirmado em '{nome_real}' (automation_id={automation_id}; protegido={protegido}) "
                f"na janela '{titulo}'. O controle nao confirmou o valor solicitado.")
    return str(resultado.get("resultado") or "Acao concluida.")

def clicar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("clicar", alvo_janela, alvo, indice)

def preencher_elemento_windows(alvo_janela="", alvo="", texto="", indice=1, permitir_protegido=False):
    return _executar_acao_ui_windows("preencher", alvo_janela, alvo, indice, texto, permitir_protegido)

def alternar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("alternar", alvo_janela, alvo, indice)

def selecionar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("selecionar", alvo_janela, alvo, indice)

_AUDIO_CLSID_MMDEVICE_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"

_AUDIO_IID_MMDEVICE_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"

_AUDIO_IID_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

_AUDIO_CLSCTX_ALL = 0x17

_AUDIO_E_RENDER = 0

_AUDIO_E_CONSOLE = 0

_AUDIO_HRESULT_S_OK = 0x00000000

_AUDIO_HRESULT_S_FALSE = 0x00000001

_AUDIO_COM_RELEASE_INDEX = 2

_AUDIO_ENDPOINT_METHOD_SET_MASTER_VOLUME_SCALAR = 7

_AUDIO_ENDPOINT_METHOD_GET_MASTER_VOLUME_SCALAR = 9

_AUDIO_ENDPOINT_METHOD_SET_MUTE = 14

_AUDIO_ENDPOINT_METHOD_GET_MUTE = 15

def _audio_guid(texto):
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    guid = GUID()
    ole32 = ctypes.windll.ole32
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(GUID)]
    ole32.CLSIDFromString.restype = wintypes.LONG
    hr = ole32.CLSIDFromString(texto, ctypes.byref(guid))
    if hr != 0:
        raise OSError(f"CLSIDFromString falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")
    return guid

def _audio_com_call(interface_ptr, index, restype, argtypes, *args):
    if not interface_ptr:
        raise OSError("Interface COM de audio invalida.")

    func_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    vtable = ctypes.cast(
        interface_ptr,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    func = func_type(
        restype,
        ctypes.c_void_p,
        *argtypes,
    )(vtable[index])
    return func(interface_ptr, *args)

def _audio_release(interface_ptr):
    if not interface_ptr:
        return
    try:
        _audio_com_call(
            interface_ptr,
            _AUDIO_COM_RELEASE_INDEX,
            ctypes.c_long,
            [],
        )
    except Exception:
        pass

class _AudioEndpointContext:
    def __enter__(self):
        if os.name != "nt":
            raise OSError("Controle de audio so esta disponivel no Windows.")

        self.ole32 = ctypes.windll.ole32
        self.ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        self.ole32.CoInitialize.restype = ctypes.c_long
        self.ole32.CoUninitialize.argtypes = []
        self.ole32.CoUninitialize.restype = None
        self.ole32.CoCreateInstance.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.ole32.CoCreateInstance.restype = ctypes.c_long

        self.initialized_hr = int(self.ole32.CoInitialize(None))
        if self.initialized_hr not in (_AUDIO_HRESULT_S_OK, _AUDIO_HRESULT_S_FALSE):
            raise OSError(
                f"CoInitialize falhou: HRESULT=0x{self.initialized_hr & 0xFFFFFFFF:08X}"
            )

        self.enumerator = ctypes.c_void_p()
        clsid = _audio_guid(_AUDIO_CLSID_MMDEVICE_ENUMERATOR)
        iid_enumerator = _audio_guid(_AUDIO_IID_MMDEVICE_ENUMERATOR)
        hr = self.ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            _AUDIO_CLSCTX_ALL,
            ctypes.byref(iid_enumerator),
            ctypes.byref(self.enumerator),
        )
        if hr != 0:
            self.close()
            raise OSError(f"CoCreateInstance do enumerador falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        self.device = ctypes.c_void_p()
        hr = _audio_com_call(
            self.enumerator,
            4,
            ctypes.c_long,
            [wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)],
            _AUDIO_E_RENDER,
            _AUDIO_E_CONSOLE,
            ctypes.byref(self.device),
        )
        if hr != 0:
            self.close()
            raise OSError(f"GetDefaultAudioEndpoint falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        self.endpoint = ctypes.c_void_p()
        iid_endpoint = _audio_guid(_AUDIO_IID_ENDPOINT_VOLUME)
        hr = _audio_com_call(
            self.device,
            3,
            ctypes.c_long,
            [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
            ctypes.byref(iid_endpoint),
            _AUDIO_CLSCTX_ALL,
            None,
            ctypes.byref(self.endpoint),
        )
        if hr != 0:
            self.close()
            raise OSError(f"Ativacao do endpoint de audio falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        return self.endpoint

    def close(self):
        _audio_release(getattr(self, "endpoint", None))
        _audio_release(getattr(self, "device", None))
        _audio_release(getattr(self, "enumerator", None))
        if getattr(self, "initialized_hr", None) in (_AUDIO_HRESULT_S_OK, _AUDIO_HRESULT_S_FALSE):
            try:
                self.ole32.CoUninitialize()
            except Exception:
                pass
        self.endpoint = None
        self.device = None
        self.enumerator = None
        self.initialized_hr = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

def _audio_hresult_ok(hr, operacao):
    if int(hr) != 0:
        raise OSError(f"{operacao} falhou: HRESULT=0x{int(hr) & 0xFFFFFFFF:08X}")

def obter_audio_windows():
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

    try:
        volume = ctypes.c_float()
        mute = wintypes.BOOL()
        with _AudioEndpointContext() as endpoint:
            hr_volume = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_GET_MASTER_VOLUME_SCALAR,
                ctypes.c_long,
                [ctypes.POINTER(ctypes.c_float)],
                ctypes.byref(volume),
            )
            _audio_hresult_ok(hr_volume, "Leitura do volume")
            hr_mute = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_GET_MUTE,
                ctypes.c_long,
                [ctypes.POINTER(wintypes.BOOL)],
                ctypes.byref(mute),
            )
            _audio_hresult_ok(hr_mute, "Leitura do mudo")

        percentual = max(0, min(100, round(float(volume.value) * 100)))
        estado = "ativado" if bool(mute.value) else "desativado"
        return f"Volume atual: {percentual}%. Mudo: {estado}."
    except Exception as erro:
        return f"Nao consegui consultar o audio do Windows: {erro}"

def definir_volume_windows(percentual):
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

    try:
        percentual = int(percentual)
    except (TypeError, ValueError):
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
        )

    if not 0 <= percentual <= 100:
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
        )

    try:
        valor = ctypes.c_float(percentual / 100.0)
        with _AudioEndpointContext() as endpoint:
            hr = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_SET_MASTER_VOLUME_SCALAR,
                ctypes.c_long,
                [ctypes.c_float, ctypes.c_void_p],
                valor,
                None,
            )
            _audio_hresult_ok(hr, "Definicao do volume")
        return f"Volume definido para {percentual}%."
    except Exception as erro:
        return f"Nao consegui definir o volume: {erro}"

def definir_mudo_windows(ativado):
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

    if not isinstance(ativado, bool):
        return ToolResult.failure(
            "O estado do mudo deve ser verdadeiro ou falso.",
            error_code="mute_state_invalid",
        )

    try:
        valor = wintypes.BOOL(1 if ativado else 0)
        with _AudioEndpointContext() as endpoint:
            hr = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_SET_MUTE,
                ctypes.c_long,
                [wintypes.BOOL, ctypes.c_void_p],
                valor,
                None,
            )
            _audio_hresult_ok(hr, "Definicao do mudo")
        return f"Mudo {'ativado' if ativado else 'desativado'}."
    except Exception as erro:
        return f"Nao consegui alterar o mudo: {erro}"

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

    try:
        yield True
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

def _configurar_api_clipboard_windows():
    """Configura assinaturas ctypes para handles/pointers Win64 corretamente."""
    user32 = _user32()
    kernel32 = ctypes.windll.kernel32

    HWND = ctypes.c_void_p
    HANDLE = ctypes.c_void_p

    user32.OpenClipboard.argtypes = [HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = HANDLE
    user32.SetClipboardData.argtypes = [ctypes.c_uint, HANDLE]
    user32.SetClipboardData.restype = HANDLE

    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = HANDLE
    kernel32.GlobalLock.argtypes = [HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [HANDLE]
    kernel32.GlobalFree.restype = HANDLE

    return user32, kernel32

def ler_area_transferencia_windows():
    if os.name != "nt":
        return "A area de transferencia global so esta disponivel no Windows."

    CF_UNICODETEXT = 13

    try:
        user32, kernel32 = _configurar_api_clipboard_windows()
        if not user32.OpenClipboard(None):
            return "Nao consegui abrir a area de transferencia."
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return "A area de transferencia nao contem texto Unicode legivel."
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return "Nao consegui ler a area de transferencia."
            try:
                texto = ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
            return texto
        finally:
            user32.CloseClipboard()
    except Exception as erro:
        try:
            user32.CloseClipboard()
        except Exception:
            pass
        return f"Nao consegui ler a area de transferencia: {erro}"

def definir_area_transferencia_windows(texto):
    if os.name != "nt":
        return "A area de transferencia global so esta disponivel no Windows."

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    try:
        user32, kernel32 = _configurar_api_clipboard_windows()
        texto = str(texto)
        dados = (texto + "\0").encode("utf-16-le")
        if not user32.OpenClipboard(None):
            return "Nao consegui abrir a area de transferencia."
        try:
            if not user32.EmptyClipboard():
                return "Nao consegui limpar a area de transferencia."
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
            if not handle:
                return "Nao consegui alocar memoria para a area de transferencia."
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return "Nao consegui preparar o texto da area de transferencia."
            try:
                ctypes.memmove(ptr, dados, len(dados))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return "Nao consegui gravar a area de transferencia."
            # A partir de SetClipboardData, a memoria passa a ser
            # propriedade do sistema; nao chamamos GlobalFree nesse caso.
            return f"Area de transferencia atualizada com {len(texto)} caracteres."
        finally:
            user32.CloseClipboard()
    except Exception as erro:
        try:
            user32.CloseClipboard()
        except Exception:
            pass
        return f"Nao consegui definir a area de transferencia: {erro}"

def listar_processos_windows(filtro=""):
    if os.name != "nt":
        return "Listagem de processos so esta disponivel no Windows."

    try:
        resultado = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=8,
            check=False,
        )
        if resultado.returncode != 0:
            return "Nao consegui listar os processos do Windows."

        linhas = list(csv.reader(io.StringIO(resultado.stdout)))
        pedido = normalizar_nome(filtro) if filtro else ""
        encontrados = []
        for linha in linhas:
            if len(linha) < 5:
                continue
            nome, pid, sessao, sessao_num, memoria = linha[:5]
            if pedido and pedido not in normalizar_nome(nome):
                continue
            encontrados.append((nome, pid, memoria))

        if not encontrados:
            if pedido:
                return f"Nenhum processo corresponde a '{filtro}'."
            return "Nenhum processo foi encontrado."

        encontrados.sort(key=lambda item: normalizar_nome(item[0]))
        limite = 25
        linhas_saida = [
            f"Processos encontrados: {len(encontrados)}" + (f" | mostrando {limite}" if len(encontrados) > limite else "")
        ]
        for nome, pid, memoria in encontrados[:limite]:
            linhas_saida.append(f"{nome} | PID {pid} | memoria {memoria}")
        return "\n".join(linhas_saida)
    except Exception as erro:
        return f"Nao consegui listar os processos: {erro}"

def encerrar_processo_windows(pid=None, nome=""):
    if os.name != "nt":
        return "Controle de processos so esta disponivel no Windows."

    alvo = str(nome).strip()
    try:
        pedido_pid = int(pid) if pid not in (None, "", 0) else None
    except (TypeError, ValueError):
        return ToolResult.failure(
            "PID invalido. Informe um numero inteiro valido.",
            error_code="pid_invalid",
        )
    if pedido_pid is not None and pedido_pid <= 0:
        return ToolResult.failure(
            "PID invalido. Informe um PID maior que zero.",
            error_code="pid_invalid",
        )
    if pedido_pid is None and not alvo:
        return "Informe um PID ou nome de processo."

    if pedido_pid is None and any(c in alvo for c in "*?"):
        return "Nao vou aceitar curingas no nome do processo; informe um executavel especifico."

    # Evita encerramento acidental de processos centrais do Windows.
    protegidos = {
        "system", "system idle process", "smss.exe", "csrss.exe", "wininit.exe",
        "services.exe", "lsass.exe", "winlogon.exe", "explorer.exe", "dwm.exe"
    }

    if pedido_pid == os.getpid():
        return "Nao vou encerrar o proprio processo do Auren pelo caminho de taskkill."

    if pedido_pid is not None:
        nome_real = _nome_executavel_por_pid_windows(pedido_pid)
        if not nome_real:
            return (
                f"Nao vou encerrar o PID {pedido_pid}: nao consegui verificar qual processo ele representa."
            )
        if nome_real in protegidos:
            return f"Nao vou encerrar o processo protegido '{nome_real}'."
    elif alvo.lower() in protegidos:
        return f"Nao vou encerrar o processo protegido '{alvo}'."

    try:
        if pedido_pid is not None:
            comando = ["taskkill", "/PID", str(pedido_pid)]
        else:
            comando = ["taskkill", "/IM", alvo]
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=10,
            check=False,
        )
        saida = (resultado.stdout or resultado.stderr).strip()
        if resultado.returncode == 0:
            return saida or "Processo encerrado."
        return f"Nao consegui encerrar o processo: {saida or 'erro desconhecido.'}"
    except Exception as erro:
        return f"Nao consegui encerrar o processo: {erro}"


def capturar_tela_windows() -> ToolResult:
    """Captura todas as telas e devolve um artefato de imagem para a rodada multimodal."""
    if os.name != "nt":
        return ToolResult.failure("Captura de tela so esta disponivel no Windows.", error_code="windows_only")

    try:
        from PIL import ImageGrab
    except Exception as exc:
        return ToolResult.failure(
            "A captura de tela precisa da dependencia Pillow. Instale Pillow para habilitar a visao de tela.",
            error_code="pillow_missing",
            data={"detalhe": str(exc)},
        )

    destino_dir = Path(__file__).resolve().parents[1] / "runtime" / "screenshots"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"screen_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
    try:
        user32 = _user32()
        with _contexto_dpi_per_monitor_windows(user32) as dpi_aplicado:
            imagem = ImageGrab.grab(all_screens=True)
            origem_x, origem_y, largura_virtual, altura_virtual = _limites_tela_virtual_windows(user32)
        imagem.save(destino, format="PNG", optimize=True)
        largura_imagem, altura_imagem = imagem.size
        return ToolResult.success(
            f"Tela capturada: {destino.name}",
            data={
                "image_path": str(destino),
                "mime_type": "image/png",
                "image_width": largura_imagem,
                "image_height": altura_imagem,
                "virtual_screen_x": origem_x,
                "virtual_screen_y": origem_y,
                "virtual_screen_width": largura_virtual,
                "virtual_screen_height": altura_virtual,
                "coordinate_space": "windows_virtual_screen_physical_pixels",
                "dpi_per_monitor_aware": bool(dpi_aplicado),
                "geometry_match": (
                    largura_imagem == largura_virtual
                    and altura_imagem == altura_virtual
                ),
            },
        )
    except Exception as exc:
        return ToolResult.failure(
            f"Nao consegui capturar a tela: {exc}",
            error_code="screenshot_failed",
        )
