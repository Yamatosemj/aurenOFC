"""Regressoes Win32 para a area de transferencia do Auren.

Sem acessar o clipboard real durante pytest: assinaturas e dependencias sao
verificadas usando DLLs simuladas. O teste funcional exige runner Windows live.
"""
from __future__ import annotations

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

from tools import windows_clipboard


class _FakeDll:
    def __getattr__(self, name: str):
        fn = Mock(name=name)
        setattr(self, name, fn)
        return fn


def test_clipboard_api_resolves_user32_from_own_module(monkeypatch):
    """Reproduz o NameError da bateria real antes do conserto."""
    user32 = _FakeDll()
    kernel32 = _FakeDll()
    monkeypatch.setattr(
        windows_clipboard.ctypes,
        "windll",
        SimpleNamespace(user32=user32, kernel32=kernel32),
        raising=False,
    )

    actual_user32, actual_kernel32 = (
        windows_clipboard._configurar_api_clipboard_windows()
    )

    assert actual_user32 is user32
    assert actual_kernel32 is kernel32
    assert user32.OpenClipboard.restype is windows_clipboard.wintypes.BOOL
    assert user32.GetClipboardData.restype is ctypes.c_void_p
    assert user32.SetClipboardData.restype is ctypes.c_void_p
    assert kernel32.GlobalAlloc.restype is ctypes.c_void_p
    assert kernel32.GlobalLock.restype is ctypes.c_void_p
