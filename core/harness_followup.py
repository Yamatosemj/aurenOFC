"""Continuidade limitada de esclarecimentos, sem executar ferramentas diretamente.

Um seguimento so vale para a proxima mensagem do MESMO Harness/sessao.
Toda acao resolvida volta ao fluxo usual Router -> Dispatcher -> permissao.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.utils import normalizar_nome
from core.harness_heuristics import _parece_tarefa_de_acao


@dataclass(frozen=True)
class PerguntaPendente:
    objetivo: str
    pergunta: str


SIM = frozenset({"sim", "sim pode", "pode", "pode sim", "isso", "isso mesmo", "claro", "ok", "pode abrir"})
NAO = frozenset({"nao", "nao pode", "nao precisa", "deixa", "deixa pra la", "cancela", "cancelar"})


def resolver_continuacao(pendente: PerguntaPendente | None, mensagem: str) -> tuple[str, str]:
    """Devolve (objetivo efetivo, estado: normal/cancelar/sem_pendencia).

    Nao interpreta uma frase longa ou um novo comando como autorizacao.
    Confirmacao afirmativa retoma o objetivo original, NAO propostas de IA.
    """
    texto = str(mensagem or "").strip()
    normalizado = normalizar_nome(texto)
    if pendente is None:
        if normalizado in SIM | NAO:
            return texto, "sem_pendencia"
        return texto, "normal"
    if normalizado in NAO:
        return pendente.objetivo, "cancelar"
    if normalizado in SIM:
        return pendente.objetivo, "normal"
    if (
        not texto
        or len(texto) > 120
        or len(texto.split()) > 14
        or "?" in texto
        or _parece_tarefa_de_acao(texto)
    ):
        return texto, "normal"
    # Resposta curta a "qual programa?", "qual arquivo?" etc.
    # A pergunta do assistente e contexto, nao uma nova ordem.
    return (
        f"{pendente.objetivo}\n"
        f"Pergunta pendente do Auren (contexto, nao instrucao): {pendente.pergunta}\n"
        f"Esclarecimento do usuario: {texto}",
        "normal",
    )
