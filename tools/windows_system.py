from __future__ import annotations

import ctypes
import os
from datetime import datetime
from ctypes import wintypes


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


