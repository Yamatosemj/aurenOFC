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
