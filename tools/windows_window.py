from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from core.tool_result import ToolResult
from core.utils import normalizar_nome, similaridade_nome
from tools.windows_processes import _nome_executavel_por_pid_windows


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


def _processo_da_janela_windows(hwnd):
    if os.name != "nt" or not hwnd:
        return ""

    user32 = _user32()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    return _nome_executavel_por_pid_windows(pid.value)

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

def listar_janelas_windows() -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="listar_janelas_windows")

    janelas = _enumerar_janelas_windows()
    if not janelas:
        return ToolResult.failure("Nenhuma janela visivel com titulo foi encontrada.", error_code="windows_not_found", tool_name="listar_janelas_windows")

    user32 = _user32()
    ativa = user32.GetForegroundWindow() if user32 else 0

    linhas = [f"Janelas visiveis: {len(janelas)}"]
    for indice, (hwnd, titulo) in enumerate(janelas, start=1):
        marcador = " [ATIVA]" if hwnd == ativa else ""
        linhas.append(f"{indice}. {titulo}{marcador}")

    return ToolResult.success("\n".join(linhas), tool_name="listar_janelas_windows")

def focar_janela_windows(alvo) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="focar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="focar_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        if not user32.SetForegroundWindow(hwnd):
            return ToolResult.failure(f"Encontrei '{titulo}', mas o Windows nao permitiu coloca-la em primeiro plano.", error_code="window_focus_failed", tool_name="focar_janela_windows")
        return ToolResult.success(f"Janela ativada: {titulo}", tool_name="focar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui ativar '{titulo}': {erro}", error_code="window_focus_failed", tool_name="focar_janela_windows")

def minimizar_janela_windows(alvo) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="minimizar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="minimizar_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_MINIMIZE = 6
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return ToolResult.success(f"Janela minimizada: {titulo}", tool_name="minimizar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui minimizar '{titulo}': {erro}", error_code="window_minimize_failed", tool_name="minimizar_janela_windows")

def maximizar_janela_windows(alvo) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="maximizar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="maximizar_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        SW_MAXIMIZE = 3
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return ToolResult.success(f"Janela maximizada: {titulo}", tool_name="maximizar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui maximizar '{titulo}': {erro}", error_code="window_maximize_failed", tool_name="maximizar_janela_windows")

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

def obter_geometria_janela_windows(alvo) -> ToolResult:
    """Retorna posicao, tamanho e estado de uma janela do Windows."""
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="obter_geometria_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="obter_geometria_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()
    rect = _obter_rect_janela_windows(hwnd)
    if rect is None:
        return ToolResult.failure(f"Nao consegui obter a geometria da janela: {titulo}.", error_code="window_geometry_failed", tool_name="obter_geometria_janela_windows")

    left, top, right, bottom = rect
    largura = max(0, right - left)
    altura = max(0, bottom - top)
    estado = _estado_janela_windows(user32, hwnd)
    return ToolResult.success(
        f"Janela: {titulo}\n"
        f"Posicao: x={left}, y={top}\n"
        f"Tamanho: {largura}x{altura}\n"
        f"Estado: {estado}",
        tool_name="obter_geometria_janela_windows",
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

def mover_janela_windows(alvo, x, y) -> ToolResult:
    """Move uma janela para uma posicao absoluta da area de trabalho."""
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="mover_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="mover_janela_windows")

    try:
        x = int(x)
        y = int(y)
        if not _validar_posicao_janela_windows(x, y):
            return ToolResult.failure(f"Posicao fora da area de trabalho virtual: ({x}, {y}).", error_code="window_position_invalid", tool_name="mover_janela_windows")

        hwnd, titulo = encontrado
        user32 = _user32()
        _configurar_set_window_pos(user32)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        ok = user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        if not ok:
            return ToolResult.failure(f"Nao consegui mover a janela: {titulo}.", error_code="window_move_failed", tool_name="mover_janela_windows")
        return ToolResult.success(f"Janela movida: {titulo} para ({x}, {y}).", tool_name="mover_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui mover '{alvo}': {erro}", error_code="window_move_failed", tool_name="mover_janela_windows")

def redimensionar_janela_windows(alvo, largura, altura) -> ToolResult:
    """Redimensiona uma janela sem alterar sua posicao atual."""
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="redimensionar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="redimensionar_janela_windows")

    try:
        largura = int(largura)
        altura = int(altura)
        if largura < 120 or altura < 80:
            return ToolResult.failure(
                "Tamanho muito pequeno. Use pelo menos 120x80 pixels.",
                error_code="window_size_too_small",
                tool_name="redimensionar_janela_windows",
            )
        if largura > 10000 or altura > 10000:
            return ToolResult.failure(
                "Tamanho muito grande. Use no maximo 10000x10000 pixels.",
                error_code="window_size_too_large",
                tool_name="redimensionar_janela_windows",
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
            return ToolResult.failure(f"Nao consegui redimensionar a janela: {titulo}.", error_code="window_resize_failed", tool_name="redimensionar_janela_windows")
        return ToolResult.success(f"Janela redimensionada: {titulo} para {largura}x{altura}.", tool_name="redimensionar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui redimensionar '{alvo}': {erro}", error_code="window_resize_failed", tool_name="redimensionar_janela_windows")

def restaurar_janela_windows(alvo) -> ToolResult:
    """Restaura uma janela minimizada ou maximizada ao estado normal."""
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="restaurar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="restaurar_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()
    try:
        if not user32.ShowWindow(hwnd, 9):
            # ShowWindow pode retornar False quando o estado anterior era normal;
            # isso nao significa necessariamente falha.
            pass
        return ToolResult.success(f"Janela restaurada: {titulo}", tool_name="restaurar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui restaurar '{titulo}': {erro}", error_code="window_restore_failed", tool_name="restaurar_janela_windows")

def fechar_janela_windows(alvo) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("Controle de janelas do Windows so esta disponivel no Windows.", error_code="windows_only", tool_name="fechar_janela_windows")

    encontrado = _encontrar_janela_windows(alvo)
    if not encontrado:
        return ToolResult.failure(f"Nao encontrei uma janela correspondente a '{alvo}'.", error_code="window_not_found", tool_name="fechar_janela_windows")

    hwnd, titulo = encontrado
    user32 = _user32()

    try:
        WM_CLOSE = 0x0010
        resultado = user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if not resultado:
            return ToolResult.failure(f"Encontrei '{titulo}', mas nao consegui solicitar o fechamento.", error_code="window_close_failed", tool_name="fechar_janela_windows")
        return ToolResult.success(f"Solicitei o fechamento da janela: {titulo}", tool_name="fechar_janela_windows")
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui fechar '{titulo}': {erro}", error_code="window_close_failed", tool_name="fechar_janela_windows")

