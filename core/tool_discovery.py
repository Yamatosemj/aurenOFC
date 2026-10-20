"""Descoberta local e limitada dos contratos ja registrados no Auren.

A descoberta apenas devolve metadados de ferramentas confiaveis. Nao executa,
autoriza, publica capabilities novas nem avalia texto vindo de sites/arquivos.
O Router decide quais schemas expor na rodada seguinte; o Dispatcher continua
sendo o unico caminho de execucao.
"""
from __future__ import annotations

import os
import re
from typing import Any

from core.tool_result import ToolResult
from core.utils import normalizar_nome

ENV_FLAG = "AUREN_DYNAMIC_TOOL_DISCOVERY"
SEARCH_NAME = "buscar_ferramentas"

SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "name": SEARCH_NAME,
    "description": (
        "Descobre ferramentas do Auren pelo nome ou pela funcao. "
        "Use quando precisar de uma capacidade que nao esta exposta. "
        "A busca NAO executa o pedido: depois dela, use o schema da ferramenta "
        "retornada na proxima rodada. Para conversas, responda normalmente."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "Capacidade desejada; por exemplo: maximizar janela, localizar arquivo."
            },
            "limite": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Quantidade maxima de ferramentas (1 a 5)."
            },
        },
        "required": ["consulta", "limite"],
        "additionalProperties": False,
    },
    "strict": True,
}

_STOP = frozenset({
    "uma", "uns", "das", "dos", "com", "para", "pela", "pelo", "que", "quero",
    "preciso", "meu", "minha", "auren", "por", "favor", "fazer", "algo",
})

_SYNONYMS = {
    "abre": "abrir", "abra": "abrir", "iniciar": "abrir", "inicie": "abrir",
    "feche": "fechar", "fecha": "fechar", "encerre": "encerrar",
    "maximize": "maximizar", "maximiza": "maximizar", "minimize": "minimizar",
    "procure": "buscar", "encontre": "buscar", "pesquise": "buscar",
    "leia": "ler", "visualize": "inspecionar", "toque": "controle",
    "musica": "midia", "audio": "audio", "volume": "volume",
    "print": "capturar", "screenshot": "capturar",
    "busque": "buscar", "localize": "buscar", "localizar": "buscar",
    "janelas": "janela", "arquivos": "arquivo", "abas": "aba",
}


def enabled() -> bool:
    """Opt-in por processo; ativar exige reiniciar o Auren."""
    return os.getenv(ENV_FLAG, "").strip() == "1"


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", normalizar_nome(str(text)).lower())
    return {_SYNONYMS.get(word, word) for word in words if word not in _STOP}


def search_catalog(consulta: str, limite: int, registered: list[dict[str, Any]]) -> ToolResult:
    """Busca deterministica em um catalogo local de schemas, sem chamadas de API."""
    query = str(consulta or "").strip()
    if not isinstance(consulta, str) or not query or len(query) > 180 or isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 5:
        return ToolResult.failure(
            "Consulta ou limite invalidos para a descoberta.",
            error_code="discovery_invalid_query", tool_name=SEARCH_NAME,
        )

    wanted = _tokens(query)
    if not wanted:
        return ToolResult.success(
            "Consulta sem palavras pesquisaveis. Seja mais especifico.",
            data={"ferramentas": []}, tool_name=SEARCH_NAME,
        )

    matches: list[tuple[int, str, str]] = []
    for tool in registered:
        name = str(tool.get("name") or "")
        if not name or name == SEARCH_NAME:
            continue
        description = str(tool.get("description") or "")
        name_terms = _tokens(name.replace("_", " "))
        description_terms = _tokens(description)
        score = 5 * len(wanted & name_terms) + len(wanted & description_terms)
        # Prefixos cobrem conjugacoes curtas sem um modelo nem dicionario externo.
        score += 2 * sum(1 for w in wanted if len(w) >= 4 and any(t.startswith(w[:4]) for t in name_terms))
        if score:
            matches.append((score, name, description[:170]))

    matches.sort(key=lambda m: (-m[0], m[1]))
    selected = [{"nome": name, "descricao": desc} for _, name, desc in matches[:limite]]
    return ToolResult.success(
        ("Ferramentas encontradas; esta consulta nao executou nenhuma acao."
         if selected else "Nenhuma capacidade encontrada no catalogo. Nao execute nem alegue ter concluido o pedido; explique o limite ou peca esclarecimento."),
        data={"ferramentas": selected}, tool_name=SEARCH_NAME,
    )


def discovered_from_round(entrada: Any, registered: list[dict[str, Any]]) -> list[str]:
    """Aceita resultados de busca SOMENTE quando ligados a function_call real.

    A rodada do Harness contem a chamada anterior (objeto SDK) e o output,
    ambos com o mesmo call_id. Nunca confia em texto que pareca um resultado.
    """
    if not isinstance(entrada, (tuple, list)):
        return []

    import json
    # Match exactly one call to exactly one output, in order. Recompute the
    # local metadata from its arguments: a matching ID alone is not provenance.
    calls = [item for item in entrada if getattr(item, "type", "") == "function_call"]
    valid = {}
    for call in calls:
        cid = getattr(call, "call_id", None)
        if (getattr(call, "name", "") != SEARCH_NAME or not isinstance(cid, str) or not cid
                or sum(getattr(c, "call_id", None) == cid for c in calls) != 1):
            continue
        try:
            args = json.loads(getattr(call, "arguments", ""))
            if not isinstance(args, dict) or set(args) != {"consulta", "limite"}:
                continue
            result = search_catalog(args["consulta"], args["limite"], registered)
            if result.ok:
                valid[cid] = (call, dict(result.data or {}))
        except (TypeError, ValueError):
            continue
    found: list[str] = []
    for index, item in enumerate(entrada):
        if not isinstance(item, dict) or item.get("type") != "function_call_output":
            continue
        cid = item.get("call_id")
        if not isinstance(cid, str) or cid not in valid:
            continue
        call, expected = valid[cid]
        if (not any(previous is call for previous in entrada[:index])
                or sum(isinstance(o, dict) and o.get("type") == "function_call_output"
                       and o.get("call_id") == cid for o in entrada) != 1):
            continue
        try:
            value = json.loads(item.get("output", ""))
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict) or value.get("ok") is not True or value.get("conteudo_nao_confiavel"):
            continue
        data = value.get("dados")
        if data != expected:
            continue
        options = data.get("ferramentas") if isinstance(data, dict) else None
        if not isinstance(options, list):
            continue
        for option in options[:5]:
            name = option.get("nome") if isinstance(option, dict) else None
            if isinstance(name, str) and name not in found:
                found.append(name)
    return found
