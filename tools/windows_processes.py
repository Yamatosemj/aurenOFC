from __future__ import annotations

import csv
import ctypes
import io
import ntpath
import os
from ctypes import wintypes
import subprocess

from core.tool_result import ToolResult
from core.utils import normalizar_nome


def _caminho_executavel_por_pid_windows(pid):
    """Consulta a imagem real do PID (falha fechada se identidade nao acessivel)."""
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
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(tamanho)):
            return buffer.value
    except Exception:
        pass
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _nome_executavel_por_pid_windows(pid):
    """Retorna o nome do executavel usando a identidade real do PID."""
    caminho = _caminho_executavel_por_pid_windows(pid)
    return ntpath.basename(caminho).lower() if caminho else ""


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

def encerrar_processo_windows(pid=None, nome="", forcar=False):
    if os.name != "nt":
        return "Controle de processos so esta disponivel no Windows."

    alvo = str(nome).strip()
    if type(forcar) is not bool:
        return ToolResult.failure(
            "O modo forcar precisa ser booleano.",
            error_code="force_invalid",
            tool_name="encerrar_processo_windows",
        )
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

    if forcar and (pedido_pid is None or not alvo):
        return ToolResult.failure(
            "Encerramento forcado exige PID e nome exato do executavel.",
            error_code="force_requires_pid_and_name",
            tool_name="encerrar_processo_windows",
        )

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
        if forcar:
            caminho_real = _caminho_executavel_por_pid_windows(pedido_pid)
            nome_real = ntpath.basename(caminho_real).lower()
            if not caminho_real or not ntpath.isabs(caminho_real):
                return ToolResult.failure(
                    f"Nao vou forcar PID {pedido_pid}: caminho do processo nao verificavel.",
                    error_code="force_identity_unverified",
                    tool_name="encerrar_processo_windows",
                )
            if nome_real != alvo.lower():
                return ToolResult.failure(
                    "Nao vou forcar: o nome informado nao corresponde ao executavel do PID.",
                    error_code="force_identity_mismatch",
                    tool_name="encerrar_processo_windows",
                )
            # Em nenhum caso usar /F para imagens do proprio Windows.
            raiz_windows = (
                getattr(os, "environ", {}).get("SystemRoot")
                or getattr(os, "environ", {}).get("WINDIR")
                or r"C:\Windows"
            )
            caminho_norm = ntpath.normcase(ntpath.normpath(caminho_real))
            raiz_norm = ntpath.normcase(ntpath.normpath(raiz_windows)).rstrip("\\")
            if caminho_norm.startswith(raiz_norm + "\\"):
                return ToolResult.failure(
                    "Nao vou forcar um executavel instalado no diretorio do Windows.",
                    error_code="force_windows_process_blocked",
                    tool_name="encerrar_processo_windows",
                )
            # Nenhuma politica por nome e exaustiva; esta e defesa adicional.
            protegidos = protegidos | {
                "svchost.exe", "registry", "memcompression",
                "taskhostw.exe", "fontdrvhost.exe", "sihost.exe",
            }
        else:
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
            if forcar:
                comando.insert(1, "/F")
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
            # taskkill /PID e /IM sem /F podem apenas enviar pedido de
            # encerramento. Codigo 0 nao prova que o PID desapareceu.
            # O Harness comprova a ausencia em nova consulta de processos.
            return ToolResult.success(
                ("Pedido de encerramento FORCADO enviado. " if forcar else
                 "Pedido de encerramento enviado. ")
                + "O processo ainda precisa ser verificado em nova listagem; "
                  "nao declare que foi encerrado.",
                data={
                    "solicitacao_enviada": True,
                    "encerramento_comprovado": False,
                    "forcado": forcar,
                    "pid": pedido_pid,
                    "nome": alvo,
                },
                tool_name="encerrar_processo_windows",
            )
        return ToolResult.failure(
            f"Nao consegui solicitar o encerramento: {saida or 'erro desconhecido.'}",
            error_code="process_termination_command_failed",
            tool_name="encerrar_processo_windows",
        )
    except Exception as erro:
        return f"Nao consegui encerrar o processo: {erro}"


