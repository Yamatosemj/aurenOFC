from __future__ import annotations

import csv
import ctypes
import io
import os
from ctypes import wintypes
from pathlib import Path
import subprocess

from core.tool_result import ToolResult
from core.utils import normalizar_nome


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

def _pids_por_nome_windows(nome: str) -> list[int]:
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {nome}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        timeout=8,
        check=False,
    )
    if resultado.returncode != 0:
        return []
    pids: list[int] = []
    for linha in csv.reader(io.StringIO(resultado.stdout)):
        if len(linha) < 2:
            continue
        try:
            pids.append(int(linha[1]))
        except (TypeError, ValueError):
            continue
    return sorted(set(pids))

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
            candidatos = _pids_por_nome_windows(alvo)
            if not candidatos:
                return f"Nenhum processo chamado '{alvo}' esta em execucao."
            if len(candidatos) > 1:
                return ToolResult.failure(
                    f"O nome '{alvo}' corresponde a {len(candidatos)} processos (PIDs: {', '.join(map(str, candidatos[:8]))}). "
                    "Informe um PID especifico para evitar encerrar varias instancias.",
                    error_code="process_name_ambiguous",
                    data={"pids": candidatos},
                    tool_name="encerrar_processo_windows",
                )
            comando = ["taskkill", "/PID", str(candidatos[0])]
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


