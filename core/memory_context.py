from __future__ import annotations

import logging
import re
from typing import Any, Iterable

_MIN_TERMO = 3
_MAX_TERMOS = 12

PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
PROMPT_MAX_PER_CATEGORY = 6
MAX_VALUE_LENGTH = 380
_MAX_KEY_LENGTH = 80
_MAX_SESSION_SUMMARY_LENGTH = 240


def termos_significativos(texto: str) -> list[str]:
    """Termos de busca uteis (>= 3 caracteres, sem repeticao, ordem preservada).

    A busca do store e por substring: termos como "o" ou "de" casam com quase
    tudo e devolvem ruido recente. Sem termos significativos nao ha busca.
    """
    vistos: dict[str, None] = {}
    for termo in re.findall(r"[\w-]+", str(texto or "").lower()):
        if len(termo) >= _MIN_TERMO:
            vistos.setdefault(termo, None)
    return list(vistos)[:_MAX_TERMOS]


def recuperar_memoria(
    store,
    objetivo: str,
    chat_id: str | None = None,
    *,
    ignorar: Iterable[str] = (),
    limite_conversas: int = 3,
    limite_estrategias: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Recupera conversas (do chat) e estrategias relevantes ao objetivo.

    `ignorar` remove conversas cujo conteudo ja esta no contexto por outro caminho
    (ex.: turnos recentes), evitando duplicar texto.
    """
    query = " ".join(termos_significativos(objetivo))
    if not query:
        return {"conversas": [], "estrategias": []}
    ja_presentes = {str(t).strip() for t in ignorar}
    conversas = store.buscar_conversas(
        query, limite=limite_conversas + len(ja_presentes), chat_id=chat_id
    ).get("resultados") or []
    conversas = [c for c in conversas if str(c.get("conteudo", "")).strip() not in ja_presentes]
    estrategias = store.buscar_estrategias(query, limite=limite_estrategias, chat_id=chat_id).get("estrategias") or []
    return {"conversas": conversas[:limite_conversas], "estrategias": estrategias}


def _normalizar_linha(valor: Any, limite: int) -> str:
    return " ".join(str(valor or "").split())[:limite]


def _intercalar_por_categoria(memorias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intercala memorias por categoria para evitar que uma categoria domine o prompt.
    Cada grupo conserva a ordem recebida e o percurso alterna entre os grupos existentes.
    Custo O(n) sobre o conjunto recebido.
    """
    grupos: dict[str, list[dict[str, Any]]] = {}
    ordem: list[str] = []
    for memoria in memorias:
        categoria = str(memoria.get("categoria") or "geral")
        if categoria not in grupos:
            grupos[categoria] = []
            ordem.append(categoria)
        grupos[categoria].append(memoria)
    saida: list[dict[str, Any]] = []
    indice = 0
    while True:
        adicionou = False
        for categoria in ordem:
            grupo = grupos[categoria]
            if indice < len(grupo):
                saida.append(grupo[indice])
                adicionou = True
        if not adicionou:
            return saida
        indice += 1


def salvar_resumo_sessao(store, chat_id: str, resumo: str) -> dict[str, Any]:
    """Persiste o resumo da sessao encerrada no store unico do Auren.
    O store aplica normalizacao, limite e filtro de credenciais antes de persistir.
    Custo O(1) de escrita SQLite.
    """
    return store.salvar_resumo_sessao(chat_id, resumo)


def pop_ultimo_resumo_sessao(store) -> dict[str, Any]:
    """Consome o resumo pendente da sessao anterior exatamente uma vez.
    A remocao ocorre dentro da transacao SQLite antes de o texto voltar ao contexto.
    Custo O(1) para o unico registro pendente.
    """
    return store.consumir_resumo_sessao()


def _formatar_core(memorias: list[dict[str, Any]], resumo_sessao: str) -> tuple[str, set[str]]:
    candidatos = _intercalar_por_categoria(memorias)
    usadas: set[str] = set()
    linhas = ["[MEMORIA PRINCIPAL]"]
    restante = PROMPT_CORE_CHARS - len(linhas[0])

    if resumo_sessao:
        linha = f"- Sessao anterior: {_normalizar_linha(resumo_sessao, _MAX_SESSION_SUMMARY_LENGTH)}"
        if len(linha) + 1 <= restante:
            linhas.append(linha)
            restante -= len(linha) + 1

    por_categoria: dict[str, int] = {}
    for memoria in candidatos:
        categoria = str(memoria.get("categoria") or "geral")
        if por_categoria.get(categoria, 0) >= PROMPT_MAX_PER_CATEGORY:
            continue
        chave = _normalizar_linha(memoria.get("chave"), _MAX_KEY_LENGTH)
        valor = _normalizar_linha(memoria.get("valor"), MAX_VALUE_LENGTH)
        if not chave or not valor:
            continue
        linha = f"- [{categoria}] {chave}: {valor}"
        if len(linha) + 1 > restante:
            continue
        linhas.append(linha)
        restante -= len(linha) + 1
        por_categoria[categoria] = por_categoria.get(categoria, 0) + 1
        usadas.add(str(memoria.get("chave") or ""))
    return "\n".join(linhas), usadas


def _formatar_indice(memorias: list[dict[str, Any]], chaves_no_core: set[str]) -> str:
    restantes = [
        memoria for memoria in _intercalar_por_categoria(memorias)
        if str(memoria.get("chave") or "") not in chaves_no_core
    ]
    if not restantes:
        return "[INDICE DE MEMORIA]\n- nenhuma chave fora do nucleo"

    prefixo = "[INDICE DE MEMORIA]\n- Chaves fora do nucleo: "
    partes: list[str] = []
    usados = len(prefixo)
    for memoria in restantes:
        chave = _normalizar_linha(memoria.get("chave"), _MAX_KEY_LENGTH)
        if not chave:
            continue
        candidato = chave if not partes else ", " + chave
        if usados + len(candidato) > PROMPT_INDEX_CHARS:
            break
        partes.append(chave)
        usados += len(candidato)

    if len(partes) < len(restantes):
        logging.getLogger("auren.memory").warning(
            "Indice de memoria excedeu o orcamento de %s; %s chaves ficaram fora do contexto.",
            PROMPT_INDEX_CHARS,
            len(restantes) - len(partes),
        )
    return prefixo + (", ".join(partes) if partes else "nenhuma chave coube")


def montar_contexto_memoria(
    store,
    objetivo: str = "",
    chat_id: str | None = None,
    *,
    max_chars: int = PROMPT_CORE_CHARS + PROMPT_INDEX_CHARS,
) -> str:
    """Monta o nucleo de memoria e um indice das chaves que ficaram de fora.
    O nucleo pode priorizar fatos relevantes ao objetivo; o indice preserva chaves omitidas.
    Custo O(n) sobre as memorias persistentes, com orcamento estrito de prompt.
    """
    del chat_id
    if store is None:
        return ""

    resultado = store.listar_memorias(limite=store.MAX_MEMORIAS)
    if not resultado.get("ok", False):
        raise RuntimeError(resultado.get("erro", "Falha ao listar memorias."))

    todas = list(resultado.get("memorias") or [])
    resumo_resultado = pop_ultimo_resumo_sessao(store)
    if not resumo_resultado.get("ok", False):
        logging.getLogger("auren.memory").warning(
            "Resumo de sessao pendente nao entrou no contexto: %s",
            resumo_resultado.get("erro", "erro desconhecido"),
        )
        resumo = ""
    else:
        resumo = str(resumo_resultado.get("resumo") or "")

    objetivo = " ".join(str(objetivo or "").split())
    if objetivo:
        termos = termos_significativos(objetivo)
        if not termos:
            if not resumo:
                return ""
            todas = []
            nucleo = []
        else:
            relevantes = store.consultar(
                " ".join(termos),
                limite=min(50, store.MAX_MEMORIAS),
            )
            if not relevantes.get("ok", False):
                raise RuntimeError(relevantes.get("erro", "Falha ao consultar memorias."))
            nucleo = list(relevantes.get("memorias") or [])
            if not nucleo:
                nucleo = todas
    else:
        nucleo = todas

    if not todas and not resumo:
        return ""

    core, usadas = _formatar_core(nucleo, resumo)
    indice = _formatar_indice(todas, usadas)
    texto = core + "\n\n" + indice
    limite_total = max(0, int(max_chars))
    if limite_total < len(texto):
        logging.getLogger("auren.memory").warning(
            "Orcamento de contexto de memoria reduzido para %s caracteres.",
            limite_total,
        )
        return texto[:limite_total]
    return texto


__all__ = [
    "PROMPT_CORE_CHARS",
    "PROMPT_INDEX_CHARS",
    "PROMPT_MAX_PER_CATEGORY",
    "MAX_VALUE_LENGTH",
    "termos_significativos",
    "recuperar_memoria",
    "montar_contexto_memoria",
    "salvar_resumo_sessao",
    "pop_ultimo_resumo_sessao",
]
