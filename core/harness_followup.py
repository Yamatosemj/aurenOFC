"""Continuidade limitada de esclarecimentos, sem executar ferramentas diretamente.

Um seguimento so vale no MESMO Harness/sessao; respostas inconclusivas nao
consomem a tarefa que aguarda informacao.
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


SIM = frozenset({"sim", "sim pode", "pode", "pode sim", "isso", "isso mesmo", "claro", "ok", "pode abrir", "sim auren", "sim auren leon sol", "pode sim auren", "claro auren", "ja disse que sim", "eu ja disse que sim", "ja confirmei", "eu ja confirmei"})
NAO = frozenset({"nao", "nao pode", "nao precisa", "deixa", "deixa pra la", "cancela", "cancelar"})


def resposta_inconclusiva(mensagem: str) -> bool:
    return normalizar_nome(mensagem) in {'', 'nao sei', 'talvez', 'nao entendi', 'ola', 'oi'}


def novo_pedido(mensagem: str) -> bool:
    texto = normalizar_nome(mensagem)
    return _parece_tarefa_de_acao(texto) or bool(re.match(
        r'^(?:auren\s+)?(?:me\s+)?(?:consulte|crie|cria|criar|lembre|lembrar|adie|adiar|agende|agendar|quero|preciso)\b', texto))


def pergunta_de_esclarecimento(objetivo: str, pergunta: str) -> bool:
    """An invitation to start a conversation does not suspend an objective.

    Keep directed questions (including confirmations) intact. This local
    filter never authorizes an action or replaces PermissionManager.
    """
    if not str(pergunta).rstrip().endswith("?"):
        return False
    goal = normalizar_nome(objetivo)
    goal = re.sub(r"\bauren\b", "", goal).strip()
    if re.fullmatch(r"(?:ola|oi|bom dia|boa tarde|boa noite|obrigad[oa]|tudo bem|vamos conversar)", goal):
        return False
    question = normalizar_nome(pergunta)
    invitation = (
        r"(?:como|em que) (?:posso|podemos) (?:te |lhe )?ajudar|"
        r"(?:posso ajudar|precisa de) (?:em )?(?:mais )?(?:alguma coisa|algo)|"
        r"sobre o que (?:quer|gostaria de) conversar"
        r"|(?:entendeu|faz sentido|e voce|esta claro)"
    )
    return re.search(r"(?:" + invitation + r")$", question) is None


def resolver_continuacao(pendente: PerguntaPendente | None, mensagem: str) -> tuple[str, str]:
    """Devolve (objetivo efetivo, estado: normal/cancelar/sem_pendencia).

    Nao interpreta uma frase longa ou um novo comando como autorizacao.
    Confirmacao afirmativa retoma o objetivo original, NAO propostas de IA.
    """
    texto = str(mensagem or "").strip()
    normalizado = normalizar_nome(texto)
    if pendente is None or not pergunta_de_esclarecimento(pendente.objetivo, pendente.pergunta):
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
        or re.match(r"^(?:auren\s+)?(?:me\s+)?(?:crie|cria|criar|lembre|lembrar|cancele|cancelar|adie|adiar|agende|agendar|quero|preciso)\b", normalizado)
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
