"""Continuidade limitada de esclarecimentos, sem executar ferramentas diretamente.

Um seguimento so vale para a proxima mensagem do MESMO Harness/sessao.
Toda acao resolvida volta ao fluxo usual Router -> Dispatcher -> permissao.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from core.utils import normalizar_nome
from core.harness_heuristics import _parece_tarefa_de_acao


@dataclass(frozen=True)
class PerguntaPendente:
    objetivo: str
    pergunta: str


SIM = frozenset({"sim", "sim pode", "pode", "pode sim", "pode ser", "isso", "isso mesmo", "claro", "ok", "pode abrir", "sim auren", "sim auren leon sol", "pode sim auren", "claro auren", "ja disse que sim", "eu ja disse que sim", "ja confirmei", "eu ja confirmei"})
NAO = frozenset({"nao", "nao pode", "nao precisa", "nao esquece isso", "esquece isso", "deixa", "deixa pra la", "cancela", "cancelar"})


def pergunta_de_esclarecimento(objetivo: str, pergunta: str) -> bool:
    """Distingue uma pergunta sobre a tarefa de um convite social."""
    if not str(pergunta).rstrip().endswith('?'):
        return False
    goal = normalizar_nome(objetivo).replace('auren', '').strip()
    if goal in {'oi', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'obrigado', 'obrigada'}:
        return False
    question = normalizar_nome(pergunta)
    return not re.search(
        r'(?:como (?:posso|podemos) (?:te |lhe )?ajudar|'
        r'precisa de (?:mais )?alguma coisa|entendeu|faz sentido|e voce)$',
        question,
    )


def resposta_inconclusiva(mensagem: str) -> bool:
    return normalizar_nome(mensagem) in {'', 'nao sei', 'talvez', 'nao entendi', 'oi', 'ola'}


def pergunta_exige_dado(pergunta: str) -> bool:
    return bool(re.search(r'\b(?:qual|quais|onde|quando|quanto|quantos|como)\b',
                          normalizar_nome(pergunta)))


def resposta_pertinente(pergunta: str, mensagem: str) -> bool:
    """Reconhece apenas escolhas curtas para as perguntas correspondentes."""
    question = normalizar_nome(pergunta)
    answer = normalizar_nome(mensagem)
    if 'resultado' in question:
        return bool(re.fullmatch(r'(?:quero|abre|abra) (?:o )?(?:primeiro|segundo|terceiro|\d+)', answer))
    if 'navegador' in question:
        return bool(re.fullmatch(r'(?:quero|prefiro) (?:o )?(?:chrome|edge|firefox|brave|opera)', answer))
    if 'aplicativo' in question or 'programa' in question:
        return bool(re.fullmatch(
            r'(?:quero (?:o|a) |prefiro (?:o |a )?)[a-z0-9.+-]+'
            r'(?: [a-z0-9.+-]+){0,2}',
            answer,
        ))
    return False


def novo_pedido(mensagem: str) -> bool:
    texto = normalizar_nome(mensagem)
    if texto.startswith('agora '):
        texto = texto[len('agora '):]
    if re.fullmatch(r'(?:que horas sao|qual e a hora)(?: agora)?', texto):
        return True
    return _parece_tarefa_de_acao(texto) or bool(re.match(
        r'^(?:auren\s+)?(?:me\s+)?(?:consulte|explique|crie|cria|criar|lembre|lembrar|agende|agendar|quero|preciso)\b',
        texto,
    ))


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
        or (_parece_tarefa_de_acao(texto) and not resposta_pertinente(pendente.pergunta, texto))
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
