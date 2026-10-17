from __future__ import annotations

import json
import ntpath
import os
from pathlib import Path
import subprocess
import shutil

from core.utils import normalizar_nome


def buscar_aplicativos_do_windows():
    comando = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-StartApps | "
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
    pedido = normalizar_nome(programa)

    if not pedido:
        return None

    candidatos = [
        pedido.replace(" ", ""),
        pedido.replace(" ", "_")
    ]

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

    for pasta in pastas:
        if not pasta.exists():
            continue

        for candidato in candidatos:
            comando = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"Get-ChildItem "
                    f"-LiteralPath {_powershell_literal(pasta)} "
                    f"-Recurse -File "
                    f"-Filter {_powershell_literal(str(candidato) + '.exe')} "
                    f"-ErrorAction SilentlyContinue | "
                    f"Select-Object -First 1 "
                    f"-ExpandProperty FullName"
                )
            ]

            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )

            caminho = resultado.stdout.strip()

            if caminho and os.path.exists(caminho):
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

def _caminho_absoluto_solicitado(programa):
    """Reconhece caminhos absolutos antes de qualquer busca fuzzy por nome."""
    nome = str(programa).strip()
    if len(nome) >= 2 and nome[0] == nome[-1] and nome[0] in ("'", '"'):
        nome = nome[1:-1].strip()
    if ntpath.isabs(nome) or os.path.isabs(nome):
        return nome
    return None


def abrir_programa(programa):
    caminho_explicito = _caminho_absoluto_solicitado(programa)
    if caminho_explicito is not None:
        # Nao substituir um caminho exato por um aplicativo encontrado por nome.
        # So aceita .exe aqui: BAT/CMD/URLs nao devem virar execucao implicita.
        if ntpath.splitext(caminho_explicito)[1].lower() != ".exe":
            return "ACAO NAO EXECUTADA: caminho explicito nao e um executavel .exe."
        if not os.path.isfile(caminho_explicito):
            return "ACAO NAO EXECUTADA: executavel solicitado nao existe ou nao e arquivo."
        try:
            subprocess.Popen(
                [caminho_explicito],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as erro:
            return f"ACAO NAO EXECUTADA: nao consegui iniciar o executavel: {erro}"
        # Popen confirma a solicitacao de inicio, nao a prontidao da GUI.
        return (
            f"Inicializacao de {ntpath.basename(caminho_explicito)} solicitada. "
            "A abertura da janela ainda nao foi verificada."
        )

    if _nome_programa_ambiguo(programa):
        return (
            "ACAO NAO EXECUTADA: nome do programa nao foi identificado "
            "com clareza. Use o nome do programa ou uma referencia resolvida "
            "pelo contexto recente."
        )

    aplicativo = encontrar_aplicativo(programa)

    if aplicativo:
        nome = aplicativo.get(
            "Name",
            programa
        )

        app_id = aplicativo.get(
            "AppID",
            ""
        )

        if app_id:
            try:
                subprocess.Popen(
                    [
                        "explorer.exe",
                        f"shell:AppsFolder\\{app_id}"
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                return f"{nome} foi aberto."

            except Exception as erro:
                return (
                    f"Nao consegui abrir "
                    f"{nome}: {erro}"
                )

    atalho = procurar_atalho(programa)

    if atalho:
        try:
            os.startfile(str(atalho))
            return f"{atalho.stem} foi aberto."

        except Exception as erro:
            return (
                f"Encontrei o atalho de "
                f"{programa}, mas nao consegui "
                f"abri-lo: {erro}"
            )

    executavel = procurar_executavel(programa)

    if executavel:
        try:
            subprocess.Popen(
                [executavel],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return (
                f"{Path(executavel).stem} foi aberto."
            )

        except Exception as erro:
            return (
                f"Nao consegui abrir "
                f"{programa}: {erro}"
            )

    caminho = shutil.which(programa)

    if (
        not caminho
        and not programa.lower().endswith(".exe")
    ):
        caminho = shutil.which(
            programa + ".exe"
        )

    if caminho:
        try:
            subprocess.Popen(
                [caminho],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return f"{programa} foi aberto."

        except Exception as erro:
            return (
                f"Nao consegui abrir "
                f"{programa}: {erro}"
            )

    return (
        f"Nao encontrei o programa "
        f"'{programa}' no Windows."
    )
