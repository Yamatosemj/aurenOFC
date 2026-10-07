from __future__ import annotations

import ctypes

from core.tool_result import ToolResult
from tools.windows_window import _user32
import os
from ctypes import wintypes

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

def ler_area_transferencia_windows() -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("A area de transferencia global so esta disponivel no Windows.", error_code="windows_only", tool_name="ler_area_transferencia_windows")

    CF_UNICODETEXT = 13

    try:
        user32, kernel32 = _configurar_api_clipboard_windows()
        if not user32.OpenClipboard(None):
            return ToolResult.failure("Nao consegui abrir a area de transferencia.", error_code="clipboard_open_failed", tool_name="ler_area_transferencia_windows")
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ToolResult.failure("A area de transferencia nao contem texto Unicode legivel.", error_code="clipboard_text_unavailable", tool_name="ler_area_transferencia_windows")
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ToolResult.failure("Nao consegui ler a area de transferencia.", error_code="clipboard_read_failed", tool_name="ler_area_transferencia_windows")
            try:
                texto = ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
            return ToolResult.success(texto, tool_name="ler_area_transferencia_windows")
        finally:
            user32.CloseClipboard()
    except Exception as erro:
        try:
            user32.CloseClipboard()
        except Exception:
            pass
        return ToolResult.failure(f"Nao consegui ler a area de transferencia: {erro}", error_code="clipboard_read_failed", tool_name="ler_area_transferencia_windows")

def definir_area_transferencia_windows(texto) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure("A area de transferencia global so esta disponivel no Windows.", error_code="windows_only", tool_name="definir_area_transferencia_windows")

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    try:
        user32, kernel32 = _configurar_api_clipboard_windows()
        texto = str(texto)
        dados = (texto + "\0").encode("utf-16-le")
        if not user32.OpenClipboard(None):
            return ToolResult.failure("Nao consegui abrir a area de transferencia.", error_code="clipboard_open_failed", tool_name="definir_area_transferencia_windows")
        try:
            if not user32.EmptyClipboard():
                return ToolResult.failure("Nao consegui limpar a area de transferencia.", error_code="clipboard_clear_failed", tool_name="definir_area_transferencia_windows")
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
            if not handle:
                return ToolResult.failure("Nao consegui alocar memoria para a area de transferencia.", error_code="clipboard_memory_allocation_failed", tool_name="definir_area_transferencia_windows")
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return ToolResult.failure("Nao consegui preparar o texto da area de transferencia.", error_code="clipboard_memory_lock_failed", tool_name="definir_area_transferencia_windows")
            try:
                ctypes.memmove(ptr, dados, len(dados))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return ToolResult.failure("Nao consegui gravar a area de transferencia.", error_code="clipboard_write_failed", tool_name="definir_area_transferencia_windows")
            # A partir de SetClipboardData, a memoria passa a ser
            # propriedade do sistema; nao chamamos GlobalFree nesse caso.
            return ToolResult.success(f"Area de transferencia atualizada com {len(texto)} caracteres.", tool_name="definir_area_transferencia_windows")
        finally:
            user32.CloseClipboard()
    except Exception as erro:
        try:
            user32.CloseClipboard()
        except Exception:
            pass
        return ToolResult.failure(f"Nao consegui definir a area de transferencia: {erro}", error_code="clipboard_write_failed", tool_name="definir_area_transferencia_windows")

