"""Politica conservadora de alvos do taskkill no Windows.

Este modulo e puro: nao consulta nem encerra processos. A permissao do usuario
continua exclusiva do PermissionManager; estas guardas valem inclusive para
chamadas diretas ao executor.
"""
from __future__ import annotations

import ntpath


# Protecao identica em modo normal e forcado, por /PID e por /IM.
# Uma lista de nomes nunca substitui a verificacao de identidade do PID.
PROTECTED_PROCESS_NAMES = frozenset({
    "system", "system idle process", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe", "explorer.exe", "dwm.exe",
    "svchost.exe", "registry", "memcompression", "taskhostw.exe",
    "fontdrvhost.exe", "sihost.exe",
})


def is_protected_process_name(name: str) -> bool:
    """Aplica a mesma allowlist negativa a todas as modalidades de taskkill."""
    return str(name or "").strip().casefold() in PROTECTED_PROCESS_NAMES


def is_inside_windows_directory(executable_path: str, windows_root: str) -> bool:
    """Confere limite de componente de diretório, não prefixo textual simples."""
    if not executable_path or not windows_root:
        return False
    path = ntpath.normcase(ntpath.normpath(executable_path))
    root = ntpath.normcase(ntpath.normpath(windows_root)).rstrip("\\")
    return bool(root and path.startswith(root + "\\"))
