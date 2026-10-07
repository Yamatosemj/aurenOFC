from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from core.utils import normalizar_nome
from tools.file_intelligence import _classify_read_path, _is_reparse_point


def interpretar_periodo(consulta):
    pedido = normalizar_nome(consulta)
    hoje = datetime.now().date()

    if "hoje" in pedido:
        return (
            hoje,
            hoje,
            f"hoje ({hoje.strftime('%d/%m/%Y')})"
        )

    if "ontem" in pedido:
        ontem = hoje - timedelta(days=1)

        return (
            ontem,
            ontem,
            f"ontem ({ontem.strftime('%d/%m/%Y')})"
        )

    if (
        "semana passada" in pedido
        or "semana anterior" in pedido
    ):
        inicio = hoje - timedelta(
            days=hoje.weekday() + 7
        )
        fim = inicio + timedelta(days=6)

        return (
            inicio,
            fim,
            (
                f"semana passada "
                f"({inicio.strftime('%d/%m/%Y')} a "
                f"{fim.strftime('%d/%m/%Y')})"
            )
        )

    if (
        "esta semana" in pedido
        or "essa semana" in pedido
    ):
        inicio = hoje - timedelta(
            days=hoje.weekday()
        )

        return (
            inicio,
            hoje,
            (
                f"esta semana "
                f"({inicio.strftime('%d/%m/%Y')} a "
                f"{hoje.strftime('%d/%m/%Y')})"
            )
        )

    return None, None, None

def buscar_arquivo(consulta):
    pedido = normalizar_nome(consulta)

    inicio, fim, descricao = interpretar_periodo(
        consulta
    )

    userprofile = Path(
        os.environ.get("USERPROFILE", "")
    )

    onedrive_roots = []
    for nome_env in (
        "OneDrive",
        "OneDriveConsumer",
        "OneDriveCommercial",
    ):
        valor = os.environ.get(nome_env, "").strip()
        if valor:
            raiz = Path(valor)
            if raiz not in onedrive_roots:
                onedrive_roots.append(raiz)

    downloads = userprofile / "Downloads"
    desktop = userprofile / "Desktop"
    documentos = userprofile / "Documents"

    desktop_candidatos = [desktop]
    documentos_candidatos = [documentos]
    downloads_candidatos = [downloads]

    for raiz in onedrive_roots:
        desktop_candidatos.extend([raiz / "Desktop", raiz / "Área de Trabalho"])
        documentos_candidatos.extend([raiz / "Documents", raiz / "Documentos"])
        downloads_candidatos.append(raiz / "Downloads")

    def _pastas_unicas_existentes(candidatas):
        resultado = []
        vistos = set()
        for pasta in candidatas:
            try:
                chave = str(pasta.resolve()).lower()
            except OSError:
                chave = str(pasta).lower()
            if chave in vistos or not pasta.exists():
                continue
            vistos.add(chave)
            resultado.append(pasta)
        return resultado

    downloads = _pastas_unicas_existentes(downloads_candidatos)
    desktop = _pastas_unicas_existentes(desktop_candidatos)
    documentos = _pastas_unicas_existentes(documentos_candidatos)

    if "download" in pedido:
        pastas = downloads

    elif (
        "desktop" in pedido
        or "area de trabalho" in pedido
    ):
        pastas = desktop

    elif (
        "documento" in pedido
        or "documentos" in pedido
    ):
        pastas = documentos

    else:
        pastas = _pastas_unicas_existentes(
            [*downloads, *desktop, *documentos]
        )

    tipos = {
        "pdf": [".pdf"],
        "txt": [".txt"],
        "texto": [".txt"],
        "zip": [".zip"],
        "rar": [".rar"],
        "word": [".doc", ".docx"],
        "excel": [".xls", ".xlsx"],
        "imagem": [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp"
        ],
        "foto": [
            ".jpg",
            ".jpeg",
            ".png",
            ".heic",
            ".webp"
        ],
        "video": [
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".webm"
        ],
        "audio": [
            ".mp3",
            ".wav",
            ".flac",
            ".m4a"
        ]
    }

    extensoes = []

    for palavra, lista in tipos.items():
        if palavra in pedido.split():
            for extensao in lista:
                if extensao not in extensoes:
                    extensoes.append(extensao)

    ignoradas = {
        "arquivo",
        "arquivos",
        "baixei",
        "baixado",
        "baixados",
        "baixada",
        "baixadas",
        "hoje",
        "ontem",
        "semana",
        "passada",
        "anterior",
        "esta",
        "essa",
        "ultima",
        "ultimo",
        "download",
        "downloads",
        "pasta",
        "pastas",
        "desktop",
        "area",
        "trabalho",
        "documento",
        "documentos",
        "meu",
        "minha",
        "meus",
        "minhas",
        "qual",
        "quais",
        "que",
        "eu",
        "diga",
        "procurar",
        "procura",
        "procure",
        "encontrar",
        "encontra",
        "encontre"
    }

    termos = [
        termo
        for termo in pedido.split()
        if termo not in ignoradas
        and termo not in tipos
        and not termo.isdigit()
    ]

    candidatos = []

    for pasta in pastas:
        if not pasta.exists():
            continue

        try:
            for current, directories, filenames in os.walk(pasta, followlinks=False):
                current_path = Path(current)
                directories[:] = [
                    nome for nome in directories
                    if not _is_reparse_point(current_path / nome)
                ]

                for filename in filenames:
                    arquivo = current_path / filename
                    if _is_reparse_point(arquivo):
                        continue
                    if not arquivo.is_file():
                        continue

                    try:
                        resolvido = arquivo.resolve(strict=True)
                        politica = _classify_read_path(resolvido)
                        if politica.status != "allowed":
                            continue
                        estatisticas = resolvido.stat()
                    except OSError:
                        continue

                    modificacao = datetime.fromtimestamp(
                        estatisticas.st_mtime
                    )
                    data_arquivo = modificacao.date()

                    if inicio is not None and (
                        data_arquivo < inicio
                        or data_arquivo > fim
                    ):
                        continue

                    if extensoes and resolvido.suffix.lower() not in extensoes:
                        continue

                    nome_normalizado = normalizar_nome(resolvido.name)
                    pontuacao = sum(
                        3
                        for termo in termos
                        if termo in nome_normalizado
                    )

                    candidatos.append(
                        (
                            pontuacao,
                            estatisticas.st_mtime,
                            resolvido,
                        )
                    )
        except OSError:
            continue
    if not candidatos:
        if descricao:
            return (
                f"Nao encontrei arquivos em "
                f"{descricao}."
            )

        return (
            "Nao encontrei arquivos "
            "correspondentes."
        )

    candidatos.sort(
        key=lambda item: (
            item[0],
            item[1]
        ),
        reverse=True
    )

    linhas = []

    if descricao:
        linhas.append(
            f"Arquivos encontrados em {descricao}:"
        )
    else:
        linhas.append(
            "Arquivos encontrados:"
        )

    linhas.append(
        "A data abaixo e a data de modificacao "
        "do arquivo no Windows."
    )

    for indice, (
        pontuacao,
        timestamp,
        arquivo
    ) in enumerate(
        candidatos[:10],
        start=1
    ):
        data = datetime.fromtimestamp(
            timestamp
        ).strftime(
            "%d/%m/%Y %H:%M"
        )

        linhas.append(
            f"{indice}. {arquivo.name} | "
            f"{data} | "
            f"{arquivo}"
        )

    return "\n".join(linhas)
