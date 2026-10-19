from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import shutil
import time
from threading import Lock

_catalog_lock = Lock()
_catalog_cache = None
_catalog_expires = 0.0
CATALOG_TTL_SECONDS = 60.0

from core.utils import caminho_explicito_programa, normalizar_nome
from core.tool_result import ToolResult


def _buscar_aplicativos_do_windows():
    comando = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-StartApps | "
            "Select-Object Name,AppID | "
            "ConvertTo-Json -Compress"
        )
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=12,
        check=False,
    )

    if (
        resultado.returncode != 0
        or not resultado.stdout.strip()
    ):
        return []

    try:
        dados = json.loads(resultado.stdout)

        if isinstance(dados, dict):
            dados = [dados]

        return dados

    except json.JSONDecodeError:
        return []


def buscar_aplicativos_do_windows():
    """Short process-local catalog cache; failed lookups never poison it."""
    global _catalog_cache, _catalog_expires
    with _catalog_lock:
        now = time.monotonic()
        if _catalog_cache is not None and now < _catalog_expires:
            return [dict(app) for app in _catalog_cache]
        apps = _buscar_aplicativos_do_windows()
        apps = [app for app in apps if isinstance(app, dict)]
        if apps:
            _catalog_cache = tuple(dict(app) for app in apps)
            _catalog_expires = time.monotonic() + CATALOG_TTL_SECONDS
        return apps

def encontrar_aplicativo(nome):
    pedido = normalizar_nome(nome)

    if not pedido:
        return None

    aplicativos = buscar_aplicativos_do_windows()

    for aplicativo in aplicativos:
        nome_app = normalizar_nome(
            aplicativo.get("Name", "")
        )

        if nome_app == pedido:
            return aplicativo

    palavras = set(pedido.split())

    melhor = None
    melhor_pontuacao = 0

    for aplicativo in aplicativos:
        nome_app = normalizar_nome(
            aplicativo.get("Name", "")
        )

        if not nome_app:
            continue

        pontuacao = len(
            palavras.intersection(
                set(nome_app.split())
            )
        )

        if pedido in nome_app:
            pontuacao += 2

        if nome_app in pedido:
            pontuacao += 2

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = aplicativo

    return melhor

def procurar_atalho(nome):
    pedido = normalizar_nome(nome)

    locais = [
        Path(
            os.environ.get("APPDATA", "")
        ) / "Microsoft/Windows/Start Menu/Programs",

        Path(
            os.environ.get("PROGRAMDATA", "")
        ) / "Microsoft/Windows/Start Menu/Programs",

        Path(
            os.environ.get("USERPROFILE", "")
        ) / "Desktop",

        Path(
            os.environ.get("PUBLIC", "")
        ) / "Desktop",

        Path(
            os.environ.get("OneDrive", "")
        ) / "Desktop",

        Path(
            os.environ.get("OneDrive", "")
        ) / "Área de Trabalho",
    ]

    melhor = None
    melhor_pontuacao = 0

    for pasta in locais:
        if not pasta.exists():
            continue

        try:
            for arquivo in pasta.rglob("*.lnk"):
                nome_atalho = normalizar_nome(
                    arquivo.stem
                )

                if not nome_atalho:
                    continue

                if nome_atalho == pedido:
                    pontuacao = 100
                else:
                    pontuacao = len(
                        set(pedido.split()).intersection(
                            set(nome_atalho.split())
                        )
                    )

                    if pedido in nome_atalho:
                        pontuacao += 2

                    if nome_atalho in pedido:
                        pontuacao += 2

                if pontuacao > melhor_pontuacao:
                    melhor_pontuacao = pontuacao
                    melhor = arquivo

        except OSError:
            continue

    return melhor

def _powershell_literal(valor):
    """Escapa uma string para um literal entre aspas simples do PowerShell."""
    return "'" + str(valor).replace("'", "''") + "'"

def procurar_executavel(programa):
    # PATH is bounded and cheap; do not recurse through installed programs first.
    caminho = shutil.which(programa)
    if not caminho and not programa.lower().endswith(".exe"):
        caminho = shutil.which(programa + ".exe")
    if caminho:
        return caminho
    pedido = normalizar_nome(programa)

    if not pedido:
        return None

    candidatos = list(dict.fromkeys([
        pedido.replace(" ", ""),
        pedido.replace(" ", "_")
    ]))

    for palavra in pedido.split():
        if palavra not in candidatos:
            candidatos.append(palavra)

    pastas = [
        Path(
            os.environ.get("LOCALAPPDATA", "")
        ) / "Programs",
        Path(
            os.environ.get("LOCALAPPDATA", "")
        ),
        Path(
            os.environ.get("PROGRAMFILES", "")
        ),
        Path(
            os.environ.get("PROGRAMFILES(X86)", "")
        )
    ]

    # One enumeration for all names/roots, one overall subprocess timeout.
    roots = list(dict.fromkeys(str(p) for p in pastas if p.exists()))
    if not roots:
        return None
    paths = ",".join(_powershell_literal(p) for p in roots)
    names = ",".join(_powershell_literal(c + '.exe') for c in candidatos)
    resultado = subprocess.run([
        "powershell", "-NoProfile", "-Command",
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        f"$aurenNames=@({names}); Get-ChildItem -LiteralPath {paths} "
        "-Recurse -File -Filter '*.exe' -ErrorAction SilentlyContinue | "
        "Where-Object { $aurenNames -contains $_.Name } | "
        "Select-Object -First 1 -ExpandProperty FullName"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20, check=False)
    caminho = resultado.stdout.strip()
    if resultado.returncode == 0 and caminho and os.path.isfile(caminho):
        return caminho

    return None

def _nome_programa_ambiguo(programa):
    texto = normalizar_nome(programa)
    if not texto:
        return True

    frases_ambiguous = (
        "o programa que foi aberto anteriormente",
        "o programa anterior",
        "programa anterior",
        "o ultimo programa",
        "ultimo programa",
        "o mesmo programa",
        "mesmo programa",
        "o aplicativo anterior",
        "aplicativo anterior",
        "o app anterior",
        "app anterior",
        "aquele programa",
        "aquela programa",
        "aquele aplicativo",
        "aquele app",
        "o mesmo",
        "mesmo",
        "isso",
        "aquilo",
    )
    return any(frase in texto for frase in frases_ambiguous)

def abrir_programa(programa):
    raw = caminho_explicito_programa(programa)
    if raw is not None:
        # Um caminho explicito nunca participa da descoberta aproximada por nome.
        try:
            target = Path(raw).expanduser().resolve(strict=True)
            if not target.is_file() or target.suffix.lower() != ".exe":
                return ToolResult.failure("O caminho deve identificar um executavel .exe existente.", error_code="explicit_executable_invalid")
            process = subprocess.Popen([str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ToolResult.success(
                f"Solicitei a abertura do executavel: {target}. A janela pronta ainda nao foi verificada.",
                data={"caminho": str(target), "pid": process.pid, "abertura_solicitada": True},
                tool_name="abrir_programa")
        except (OSError, ValueError, RuntimeError) as exc:
            return ToolResult.failure(f"Nao consegui abrir o executavel solicitado: {exc}", error_code="explicit_executable_failed", tool_name="abrir_programa")

    if _nome_programa_ambiguo(programa):
        return ToolResult.failure(
            "Nome do programa nao identificado com clareza. Informe o nome ou caminho.",
            error_code="application_ambiguous", tool_name="abrir_programa")

    # Discovery is read-only. A failed/uncertain launch never starts a second
    # launch path: the first effect might already have happened.
    try:
        try:
            aplicativo = encontrar_aplicativo(programa)
        except (subprocess.TimeoutExpired, OSError):
            aplicativo = None  # safe discovery fallback, no launch attempted
        if aplicativo and aplicativo.get("AppID"):
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aplicativo['AppID']}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return _abertura_solicitada(aplicativo.get("Name", programa), "catalog")
        atalho = procurar_atalho(programa)
        if atalho:
            os.startfile(str(atalho))
            return _abertura_solicitada(atalho.stem, "shortcut")
        executavel = procurar_executavel(programa)
        if executavel:
            process = subprocess.Popen([executavel], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return _abertura_solicitada(Path(executavel).stem, "executable", process.pid)
    except subprocess.TimeoutExpired:
        return ToolResult.failure("A busca do programa excedeu o tempo esperado. Informe o caminho completo para tentar novamente.",
            error_code="application_search_timeout", tool_name="abrir_programa")
    except PermissionError:
        return ToolResult.failure("O Windows negou acesso ao programa. Nao tentei abri-lo por outro caminho.",
            error_code="application_access_denied", tool_name="abrir_programa")
    except OSError:
        return ToolResult.failure("Nao consegui solicitar a abertura do programa. O resultado nao foi confirmado; nao repeti a operacao.",
            error_code="application_launch_failed", tool_name="abrir_programa")
    return ToolResult.failure(f"Nao encontrei o programa '{programa}' no Windows.",
        error_code="application_not_found", tool_name="abrir_programa")


def _abertura_solicitada(nome, source, pid=None):
    return ToolResult.success(
        f"Solicitei a abertura de {nome}. A janela pronta ainda nao foi verificada.",
        data={"abertura_solicitada": True, "janela_verificada": False, "source": source, "pid": pid},
        tool_name="abrir_programa")
