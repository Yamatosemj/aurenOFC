from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.undo import push_undo
from core.utils import normalizar_nome
from core.tool_result import ToolResult
from tools import file_intelligence
from tools.file_intelligence import (
    _classify_read_path,
    _classify_write_path,
    _is_reparse_point,
    _rename_destination,
    _resolve_path,
    _sha256,
)

MAX_SEARCH_FILES = 10_000
MAX_SEARCH_SECONDS = 5.0


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

def buscar_arquivo(consulta) -> ToolResult:
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
    arquivos_inspecionados = 0
    inicio_scan = time.monotonic()
    scan_interrompido = False

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
                    if (pelos_menos := arquivos_inspecionados) >= MAX_SEARCH_FILES or time.monotonic() - inicio_scan >= MAX_SEARCH_SECONDS:
                        scan_interrompido = True
                        break
                    arquivos_inspecionados = pelos_menos + 1
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
                if scan_interrompido:
                    break
        except OSError:
            continue
    if not candidatos:
        if descricao:
            return ToolResult.failure(
                f"Nao encontrei arquivos em "
                f"{descricao}.",
                error_code="files_not_found",
                tool_name="buscar_arquivo",
            )

        return ToolResult.failure(
            "Nao encontrei arquivos "
            "correspondentes.",
            error_code="files_not_found",
            tool_name="buscar_arquivo",
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

    if scan_interrompido:
        linhas.append(
            f"Busca interrompida pelo limite de seguranca ({MAX_SEARCH_FILES} arquivos ou {MAX_SEARCH_SECONDS:.1f}s)."
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

    return ToolResult.success(
        "\n".join(linhas),
        tool_name="buscar_arquivo",
    )


# Flags da Shell API. FOF_ALLOWUNDO faz com que a exclusao seja enviada a
# Lixeira do Windows, nunca apagada diretamente.
_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_FOF_NORECURSEREPARSE = 0x8000


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("wFunc", ctypes.wintypes.UINT),
        ("pFrom", ctypes.wintypes.LPCWSTR),
        ("pTo", ctypes.wintypes.LPCWSTR),
        ("fFlags", ctypes.wintypes.UINT),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings", ctypes.wintypes.LPVOID),
        ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
    ]


def _falha_caminho(tool_name: str, policy, caminho: str) -> ToolResult:
    return ToolResult.failure(
        f"Operacao bloqueada para '{caminho}': {policy.motivo}",
        error_code="path_not_allowed",
        data={"caminho": policy.caminho_resolvido, "motivo": policy.motivo},
        tool_name=tool_name,
    )


def _validar_fonte_arquivo(caminho: str, tool_name: str):
    policy = _classify_write_path(caminho)
    if policy.status != "allowed":
        return None, _falha_caminho(tool_name, policy, caminho)
    path = Path(policy.caminho_resolvido)
    try:
        path.lstat()
    except FileNotFoundError:
        return None, ToolResult.failure(
            f"Arquivo nao encontrado: {path}",
            error_code="path_not_found",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    except OSError as exc:
        return None, ToolResult.failure(
            f"Nao foi possivel acessar o arquivo: {exc}",
            error_code="path_inaccessible",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    if _is_reparse_point(path):
        return None, ToolResult.failure(
            f"Operacao bloqueada: o arquivo e um link/reparse point: {path}",
            error_code="path_not_allowed",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    if not path.is_file():
        return None, ToolResult.failure(
            f"O caminho informado nao e um arquivo regular: {path}",
            error_code="not_a_file",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    return path, None


def _validar_destino(caminho: str, tool_name: str):
    policy = _classify_write_path(caminho)
    if policy.status != "allowed":
        return None, _falha_caminho(tool_name, policy, caminho)
    path = Path(policy.caminho_resolvido)
    if os.path.lexists(str(path)):
        return None, ToolResult.failure(
            f"O destino ja existe e nao sera sobrescrito: {path}",
            error_code="destination_exists",
            data={"destino": str(path)},
            tool_name=tool_name,
        )

    parent_policy = _classify_write_path(str(path.parent))
    if parent_policy.status != "allowed":
        return None, _falha_caminho(tool_name, parent_policy, str(path.parent))
    parent = Path(parent_policy.caminho_resolvido)
    try:
        parent_stat = parent.lstat()
    except FileNotFoundError:
        return None, ToolResult.failure(
            f"A pasta pai nao existe: {parent}",
            error_code="parent_not_found",
            data={"destino": str(path), "pasta_pai": str(parent)},
            tool_name=tool_name,
        )
    except OSError as exc:
        return None, ToolResult.failure(
            f"Nao foi possivel acessar a pasta pai: {exc}",
            error_code="parent_inaccessible",
            data={"destino": str(path), "pasta_pai": str(parent)},
            tool_name=tool_name,
        )
    if _is_reparse_point(parent) or not parent.is_dir():
        return None, ToolResult.failure(
            f"A pasta pai do destino nao e um diretorio seguro: {parent}",
            error_code="parent_not_allowed",
            data={"destino": str(path), "pasta_pai": str(parent)},
            tool_name=tool_name,
        )
    return path, None


def _undo_mover_arquivo(origem: Path, destino: Path, expected_hash: str) -> ToolResult:
    try:
        origem_policy = _classify_write_path(str(origem))
        destino_policy = _classify_write_path(str(destino))
        if origem_policy.status != "allowed" or destino_policy.status != "allowed":
            return ToolResult.failure(
                "Nao foi possivel restaurar o arquivo porque origem ou destino deixou de ser permitido.",
                error_code="undo_path_not_allowed",
                tool_name="desfazer_ultima_acao",
            )
        if origem.exists():
            return ToolResult.failure(
                "Nao foi possivel restaurar o arquivo porque a origem ja voltou a existir.",
                error_code="undo_source_exists",
                tool_name="desfazer_ultima_acao",
            )
        if not destino.is_file() or _is_reparse_point(destino):
            return ToolResult.failure(
                "Nao foi possivel restaurar: o destino atual nao e um arquivo regular seguro.",
                error_code="undo_target_missing",
                tool_name="desfazer_ultima_acao",
            )
        if _sha256(destino) != expected_hash:
            return ToolResult.failure(
                "Nao foi possivel restaurar porque o arquivo movido foi alterado depois da acao.",
                error_code="undo_target_changed",
                tool_name="desfazer_ultima_acao",
            )
        shutil.move(str(destino), str(origem))
        return ToolResult.success(
            f"Arquivo restaurado para {origem}.",
            tool_name="desfazer_ultima_acao",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao restaurar o arquivo: {exc}",
            error_code="undo_restore_failed",
            tool_name="desfazer_ultima_acao",
        )


def _undo_copia_arquivo(destino: Path, expected_hash: str) -> ToolResult:
    try:
        policy = _classify_write_path(str(destino))
        if policy.status != "allowed":
            return ToolResult.failure(
                "Nao foi possivel remover a copia porque o destino deixou de ser permitido.",
                error_code="undo_path_not_allowed",
                tool_name="desfazer_ultima_acao",
            )
        if not destino.is_file() or _is_reparse_point(destino):
            return ToolResult.failure(
                "Nao foi possivel remover a copia: o arquivo criado pelo Auren nao esta mais disponivel como arquivo regular.",
                error_code="undo_target_missing",
                tool_name="desfazer_ultima_acao",
            )
        if _sha256(destino) != expected_hash:
            return ToolResult.failure(
                "A copia foi alterada depois da criacao; para evitar apagar dados do usuario, o undo foi recusado.",
                error_code="undo_target_changed",
                tool_name="desfazer_ultima_acao",
            )
        destino.unlink()
        return ToolResult.success(
            f"Copia removida: {destino}.",
            tool_name="desfazer_ultima_acao",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao remover a copia: {exc}",
            error_code="undo_copy_remove_failed",
            tool_name="desfazer_ultima_acao",
        )


def _undo_criar_pasta(pasta: Path) -> ToolResult:
    try:
        policy = _classify_write_path(str(pasta))
        if policy.status != "allowed":
            return ToolResult.failure(
                "Nao foi possivel remover a pasta porque ela deixou de ser permitida.",
                error_code="undo_path_not_allowed",
                tool_name="desfazer_ultima_acao",
            )
        if not pasta.exists():
            return ToolResult.success("A pasta ja nao existe.", tool_name="desfazer_ultima_acao")
        if not pasta.is_dir() or _is_reparse_point(pasta):
            return ToolResult.failure(
                "A pasta criada pelo Auren nao esta mais disponivel como diretorio regular.",
                error_code="undo_target_changed",
                tool_name="desfazer_ultima_acao",
            )
        try:
            next(pasta.iterdir())
        except StopIteration:
            pasta.rmdir()
            return ToolResult.success(
                f"Pasta removida: {pasta}.",
                tool_name="desfazer_ultima_acao",
            )
        return ToolResult.failure(
            "A pasta recebeu conteudo depois de ser criada; o undo nao remove pasta nao vazia.",
            error_code="undo_folder_not_empty",
            tool_name="desfazer_ultima_acao",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao desfazer a criacao da pasta: {exc}",
            error_code="undo_folder_remove_failed",
            tool_name="desfazer_ultima_acao",
        )


def mover_arquivo(origem: str, destino: str) -> ToolResult:
    """Move um arquivo apenas dentro das raizes permitidas e registra undo seguro.\n    Origem e destino sao validados antes da movimentacao e o undo restaura o arquivo se o destino ainda for identico.\n    Custo: O(n) para o SHA-256 do arquivo mais o custo real do movimento.\n    """
    tool_name = "mover_arquivo"
    source, failure = _validar_fonte_arquivo(origem, tool_name)
    if failure:
        return failure
    target, failure = _validar_destino(destino, tool_name)
    if failure:
        return failure
    try:
        digest = _sha256(source)
        shutil.move(str(source), str(target))
        push_undo(
            f"mover arquivo {source.name} para {target}",
            lambda source=source, target=target, digest=digest: _undo_mover_arquivo(source, target, digest),
        )
        return ToolResult.success(
            f"Arquivo movido para {target}.",
            data={"origem": str(source), "destino": str(target), "undo_registrado": True},
            tool_name=tool_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao mover o arquivo: {exc}",
            error_code="move_failed",
            data={"origem": str(source), "destino": str(target)},
            tool_name=tool_name,
        )


def copiar_arquivo(origem: str, destino: str) -> ToolResult:
    """Copia um arquivo apenas dentro das raizes permitidas e prepara undo da copia.\n    A copia usa copy2 sem modificar o original e o undo so remove a copia se ela permanecer identica.\n    Custo: O(n) pelo hash mais o custo O(n) da copia do arquivo.\n    """
    tool_name = "copiar_arquivo"
    source, failure = _validar_fonte_arquivo(origem, tool_name)
    if failure:
        return failure
    target, failure = _validar_destino(destino, tool_name)
    if failure:
        return failure
    try:
        digest = _sha256(source)
        shutil.copy2(str(source), str(target))
        push_undo(
            f"copiar arquivo {source.name} para {target}",
            lambda target=target, digest=digest: _undo_copia_arquivo(target, digest),
        )
        return ToolResult.success(
            f"Arquivo copiado para {target}.",
            data={
                "origem": str(source),
                "destino": str(target),
                "original_preservado": True,
                "undo_registrado": True,
            },
            tool_name=tool_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao copiar o arquivo: {exc}",
            error_code="copy_failed",
            data={"origem": str(source), "destino": str(target)},
            tool_name=tool_name,
        )


def renomear_arquivo(caminho: str, novo_nome: str) -> ToolResult:
    """Renomeia um arquivo dentro da mesma pasta permitida e registra undo.\n    O novo nome e convertido em destino no proprio diretorio e nunca pode virar um caminho arbitrario.\n    Custo: O(n) para validar o nome e calcular SHA-256, mais o custo do rename.\n    """
    tool_name = "renomear_arquivo"
    source, failure = _validar_fonte_arquivo(caminho, tool_name)
    if failure:
        return failure
    try:
        target = _rename_destination(str(source), novo_nome)
    except ValueError as exc:
        return ToolResult.failure(
            str(exc),
            error_code="invalid_rename",
            data={"caminho": str(source)},
            tool_name=tool_name,
        )
    target, failure = _validar_destino(str(target), tool_name)
    if failure:
        return failure
    try:
        digest = _sha256(source)
        source.rename(target)
        push_undo(
            f"renomear arquivo {source.name} para {target.name}",
            lambda source=source, target=target, digest=digest: _undo_mover_arquivo(source, target, digest),
        )
        return ToolResult.success(
            f"Arquivo renomeado para {target.name}.",
            data={"origem": str(source), "destino": str(target), "undo_registrado": True},
            tool_name=tool_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao renomear o arquivo: {exc}",
            error_code="rename_failed",
            data={"origem": str(source), "destino": str(target)},
            tool_name=tool_name,
        )


def criar_pasta(caminho: str) -> ToolResult:
    """Cria uma pasta apenas dentro das raizes permitidas e registra undo condicional.\n    A pasta nasce vazia e o undo so a remove enquanto continuar vazia e sem reparse points.\n    Custo: O(tamanho do caminho) para validacao mais o custo de uma criacao de diretorio.\n    """
    tool_name = "criar_pasta"
    target, failure = _validar_destino(caminho, tool_name)
    if failure:
        return failure
    try:
        target.mkdir()
        push_undo(
            f"criar pasta {target}",
            lambda target=target: _undo_criar_pasta(target),
        )
        return ToolResult.success(
            f"Pasta criada: {target}.",
            data={"caminho": str(target), "undo_registrado": True},
            tool_name=tool_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao criar a pasta: {exc}",
            error_code="mkdir_failed",
            data={"caminho": str(target)},
            tool_name=tool_name,
        )


def _contem_reparse_descendente(pasta: Path) -> bool:
    if not pasta.is_dir():
        return False
    try:
        for current, directories, filenames in os.walk(pasta, followlinks=False):
            current_path = Path(current)
            for nome in [*directories, *filenames]:
                candidato = current_path / nome
                try:
                    candidato.lstat()
                except OSError:
                    return True
                if _is_reparse_point(candidato):
                    return True
    except OSError:
        return True
    return False


def _enviar_para_lixeira_windows(path: Path) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure(
            "A Lixeira do Windows so pode ser usada no Windows.",
            error_code="windows_only",
            tool_name="enviar_para_lixeira",
        )

    operation = _SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = _FO_DELETE
    operation.pFrom = f"{path}\\0\\0"
    operation.pTo = None
    operation.fFlags = (
        _FOF_ALLOWUNDO
        | _FOF_NOCONFIRMATION
        | _FOF_SILENT
        | _FOF_NOERRORUI
        | _FOF_NORECURSEREPARSE
    )
    operation.fAnyOperationsAborted = False
    operation.hNameMappings = None
    operation.lpszProgressTitle = None

    try:
        shell32 = ctypes.windll.shell32
        shell32.SHFileOperationW.argtypes = [ctypes.POINTER(_SHFILEOPSTRUCTW)]
        shell32.SHFileOperationW.restype = ctypes.c_int
        result = int(shell32.SHFileOperationW(ctypes.byref(operation)))
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        return ToolResult.failure(
            f"Falha ao acionar a Lixeira do Windows: {exc}",
            error_code="trash_api_failed",
            tool_name="enviar_para_lixeira",
        )

    if result != 0 or bool(operation.fAnyOperationsAborted):
        return ToolResult.failure(
            f"A Lixeira do Windows recusou a operacao (codigo {result}).",
            error_code="trash_failed",
            data={"codigo_shfileoperation": result, "cancelada": bool(operation.fAnyOperationsAborted)},
            tool_name="enviar_para_lixeira",
        )
    return ToolResult.success(
        f"Enviado para a Lixeira do Windows: {path}.",
        data={"caminho": str(path), "lixeira": "Windows", "undo_registrado": False},
        tool_name="enviar_para_lixeira",
    )


def enviar_para_lixeira(caminho: str) -> ToolResult:
    """Envia um arquivo ou pasta permitida para a Lixeira do Windows sem exclusao permanente.\n    O caminho e validado contra a mesma allowlist de arquivos e a Shell API usa FOF_ALLOWUNDO; nenhum undo e registrado sem restauracao confiavel.\n    Custo: O(n) para validar descendentes reparse de pastas mais o custo da operacao da Shell.\n    """
    tool_name = "enviar_para_lixeira"
    policy = _classify_write_path(caminho)
    if policy.status != "allowed":
        return _falha_caminho(tool_name, policy, caminho)
    path = Path(policy.caminho_resolvido)
    if not path.exists():
        return ToolResult.failure(
            f"Caminho nao encontrado: {path}",
            error_code="path_not_found",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    if _is_reparse_point(path):
        return ToolResult.failure(
            "A Lixeira nao recebe symlink, junction ou outro reparse point.",
            error_code="path_not_allowed",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    for root in file_intelligence._read_allowed_roots():
        if path == root:
            return ToolResult.failure(
                "Pastas raiz permitidas sao protegidas contra envio para a Lixeira.",
                error_code="critical_folder_protected",
                data={"caminho": str(path)},
                tool_name=tool_name,
            )
    if path.is_dir() and _contem_reparse_descendente(path):
        return ToolResult.failure(
            "A pasta contem link, junction ou outro reparse point; envio para a Lixeira foi bloqueado.",
            error_code="reparse_descendant_blocked",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    return _enviar_para_lixeira_windows(path)
