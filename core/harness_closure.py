"""Comprovacao conservadora do estado final de pedidos de fechamento.

Uma chamada WM_CLOSE bem-sucedida apenas solicita o fechamento. Quando o
usuario pede encerrar por completo, a ausencia de janelas nao prova que
processos em segundo plano tenham terminado. Nenhuma acao e executada aqui.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from core.utils import normalizar_nome

_INICIO = re.compile(
    r"^(?:(?:auren|auren leon sol) )?"
    r"(?:feche|fecha|fechar|encerre|encerra|encerrar|termine|terminar|finalize|finalizar) "
    r"(?:(?:a|o|as|os|um|uma) )?"
)
_COMPLETO = re.compile(
    r"\b(?:por completo|porcompleto|completamente|totalmente|definitivamente|de vez)\b"
)


def _alvo_fechamento(objetivo: str) -> tuple[str, bool] | None:
    texto = normalizar_nome(objetivo)
    inicio = _INICIO.match(texto)
    if not inicio:
        return None
    alvo_bruto = texto[inicio.end():]
    completo = bool(_COMPLETO.search(alvo_bruto))
    alvo = _COMPLETO.sub("", alvo_bruto).strip()
    alvo = re.sub(r"^(?:janela|programa|app|aplicativo) (?:de |da |do )?", "", alvo)
    alvo = re.sub(r"\b(?:novamente|agora)\b$", "", alvo).strip()
    # Pedidos compostos ou indefinidos nao fornecem alvo para comprovar
    # deterministicamente. O modelo continuara sujeito aos guardas normais.
    if (
        not alvo or len(alvo) > 70
        or re.search(r"\b(?:e depois|em seguida|e abra|e feche|ou)\b", alvo)
    ):
        return None
    return alvo, completo


def _argumentos(item: Mapping[str, Any]) -> dict:
    try:
        argumentos = json.loads(str(item.get("argumentos") or "{}"))
    except (TypeError, ValueError):
        return {}
    return argumentos if isinstance(argumentos, dict) else {}


def _comprovou_fechamento(objetivo: str, historico: Sequence[Mapping[str, Any]]) -> bool:
    pedido = _alvo_fechamento(objetivo)
    if pedido is None:
        return False
    alvo, completo = pedido
    ferramentas_mutantes = {"fechar_janela_windows", "encerrar_processo_windows"}
    ultima_mutacao = max(
        (i for i, item in enumerate(historico) if item.get("ferramenta") in ferramentas_mutantes),
        default=-1,
    )
    for i, item in enumerate(historico):
        if i <= ultima_mutacao:
            continue
        ferramenta = str(item.get("ferramenta") or "")
        retorno = str(item.get("resultado") or "")
        argumentos = _argumentos(item)
        if completo:
            if ferramenta != "listar_processos_windows":
                continue
            filtro = normalizar_nome(str(argumentos.get("filtro") or ""))
            # Filtrar apenas "steam.exe" nao cobre steamwebhelper.exe; a
            # prova de fechamento integral exige o filtro do alvo inteiro.
            if not filtro or filtro != alvo:
                continue
            if retorno.startswith("Nenhum processo corresponde a '"):
                return True
        elif ferramenta == "listar_janelas_windows":
            if retorno.startswith("Nenhuma janela visivel com titulo foi encontrada."):
                return True
            if not retorno.startswith("Janelas visiveis:"):
                continue
            titulos = [
                re.sub(r"^\d+\.\s*", "", linha).replace(" [ATIVA]", "")
                for linha in retorno.splitlines()[1:]
            ]
            if all(alvo not in normalizar_nome(titulo) for titulo in titulos):
                return True
    return False


def _encerramento_sem_progresso(
    objetivo: str,
    historico: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Detecta PID/nome que continua ativo depois de taskkill.

    O resultado positivo do comando significa envio da solicitacao, nao
    encerramento. Exigimos uma consulta posterior, filtrada pelo aplicativo
    solicitado. Se o MESMO processo persistir, encerramos essa tentativa:
    insistir com o mesmo PID sem mudar o estado nao e recuperacao.
    """
    pedido = _alvo_fechamento(objetivo)
    if pedido is None or not pedido[1] or not historico:
        return None
    alvo, _completo = pedido
    ultimo = historico[-1]
    if ultimo.get("ferramenta") != "listar_processos_windows":
        return None
    argumentos_lista = _argumentos(ultimo)
    if normalizar_nome(str(argumentos_lista.get("filtro") or "")) != alvo:
        return None
    resultado = str(ultimo.get("resultado") or "")
    if not resultado.startswith("Processos encontrados:"):
        return None

    ultima_mutacao = next(
        (
            item for item in reversed(historico[:-1])
            if item.get("ferramenta") == "encerrar_processo_windows"
        ),
        None,
    )
    if ultima_mutacao is None:
        return None
    # So podemos relacionar esta leitura com a ultima tentativa quando nao
    # existe uma consulta de processos intermediaria depois dessa tentativa.
    pos_mutacao = max(
        i for i, item in enumerate(historico[:-1])
        if item is ultima_mutacao
    )
    if any(
        item.get("ferramenta") == "listar_processos_windows"
        for item in historico[pos_mutacao + 1:-1]
    ):
        return None

    args = _argumentos(ultima_mutacao)
    pid = args.get("pid")
    try:
        pid = int(pid) if pid not in (None, "", 0) else None
    except (TypeError, ValueError):
        pid = None
    nome = normalizar_nome(str(args.get("nome") or ""))
    if pid is None and not nome:
        return None

    for linha in resultado.splitlines()[1:]:
        partes = linha.split(" | PID ", 1)
        if len(partes) != 2:
            continue
        executavel = partes[0].strip()
        try:
            pid_atual = int(partes[1].split(" | ", 1)[0].strip())
        except (ValueError, TypeError):
            continue
        if pid is not None and pid_atual == pid:
            return {"pid": pid, "processo": executavel}
        if pid is None and nome == normalizar_nome(executavel):
            return {"pid": pid_atual, "processo": executavel}
    return None


def _repeticao_encerramento_sem_verificar(
    objetivo: str,
    chamadas: Sequence[Any],
    historico: Sequence[Mapping[str, Any]],
) -> bool:
    """Nao reenviar a mesma tentativa sem uma consulta entre elas."""
    pedido = _alvo_fechamento(objetivo)
    if pedido is None or not pedido[1] or not historico:
        return False
    ultima_lista = max(
        (i for i, item in enumerate(historico)
         if item.get("ferramenta") == "listar_processos_windows"),
        default=-1,
    )
    tentativas = [
        _argumentos(item)
        for item in historico[ultima_lista + 1:]
        if item.get("ferramenta") == "encerrar_processo_windows"
    ]
    if not tentativas:
        return False
    for chamada in chamadas:
        if str(getattr(chamada, "name", "")) != "encerrar_processo_windows":
            continue
        try:
            args = json.loads(str(getattr(chamada, "arguments", "") or "{}"))
        except (ValueError, TypeError):
            continue
        if not isinstance(args, dict):
            continue
        if any(
            args.get("pid") == anterior.get("pid")
            and args.get("nome") == anterior.get("nome")
            for anterior in tentativas
        ):
            return True
    return False


def _orientacao_verificacao(objetivo: str) -> str:
    pedido = _alvo_fechamento(objetivo)
    if pedido is None:
        return ""
    alvo, completo = pedido
    if completo:
        return (
            f"Ainda nao esta comprovado o encerramento completo de '{alvo}'. "
            f"Use listar_processos_windows com filtro='{alvo}' para verificar. "
            "Se o processo existir, avalie a proxima acao segura respeitando "
            "verificacao de intencao, PermissionManager e confirmacao do usuario. "
            "Fechar a janela nao comprova encerramento de processos."
        )
    return (
        f"Ainda nao esta comprovado o fechamento da janela de '{alvo}'. "
        "Uma resposta de fechar_janela_windows apenas solicita WM_CLOSE. "
        "Use listar_janelas_windows para verificar se a janela sumiu "
        "antes de informar conclusao."
    )
