from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

def _configurar_api_clipboard_windows():
    """Configura assinaturas ctypes para handles/pointers Win64 corretamente."""
    # Usa a API nativa diretamente: este modulo nao define _user32().
    # _user32 existe em outras fachadas Windows e nao deve ser assumido aqui.
    user32 = ctypes.windll.user32
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

