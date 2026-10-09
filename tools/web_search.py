from __future__ import annotations

from typing import Any

from core.tool_result import ToolResult

MAX_SOURCES = 8
MAX_SNIPPET_CHARS = 600
MAX_TOTAL_CHARS = 5000
MODOS = ("news", "research", "price", "compare")

_MODE_INSTRUCTIONS = {
    "news": "Priorize informacao recente e noticias. Diferencie fatos publicados de opiniao.",
    "research": "Priorize fontes primarias, tecnicas ou institucionais e cubra pontos de vista relevantes com mais profundidade.",
    "price": "Priorize precos atuais, moeda, disponibilidade e data da informacao. Nao invente preco quando a fonte nao informa.",
    "compare": "Compare explicitamente as opcoes pedidas, buscando dados equivalentes e fontes independentes quando possivel.",
}


def _texto_seguro(valor: Any, limite: int) -> str:
    """Converte texto externo em trecho limitado para o ToolResult.
    A funcao corta por tamanho antes de devolver conteudo da web ao modelo.
    Custo: O(n) no tamanho do texto recebido."""
    texto = " ".join(str(valor or "").split())
    if len(texto) > limite:
        return texto[: max(0, limite - 1)] + "…"
    return texto


def _campo(obj: Any, nome: str, padrao: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(nome, padrao)
    return getattr(obj, nome, padrao)


def _extrair_fontes(resposta: Any) -> list[dict[str, str]]:
    """Extrai URLs e pequenos trechos da resposta hospedada de web search.
    Aceita objetos do SDK e mocks em dict sem confiar no formato de um unico SDK.
    Custo: O(k) no numero de fontes retornadas."""
    fontes: list[dict[str, str]] = []
    output = list(getattr(resposta, "output", []) or [])
    for item in output:
        if _campo(item, "type") != "web_search_call":
            continue
        action = _campo(item, "action", {})
        sources = _campo(action, "sources", []) or []
        for source in sources:
            url = _texto_seguro(_campo(source, "url"), 1000)
            if not url:
                continue
            titulo = _texto_seguro(_campo(source, "title"), 180)
            trecho = _campo(source, "snippet") or _campo(source, "description") or _campo(source, "text")
            fontes.append({
                "url": url,
                "titulo": titulo,
                "trecho": _texto_seguro(trecho, MAX_SNIPPET_CHARS),
            })
            if len(fontes) >= MAX_SOURCES:
                return fontes
    return fontes


def pesquisar_web(consulta: str, modo: str) -> ToolResult:
    """Executa a busca hospedada do provedor e devolve fontes limitadas.
    O modo apenas orienta o tipo de busca; todo resultado externo fica marcado como nao confiavel.
    Custo: uma chamada ao Responses API com web_search."""
    consulta = str(consulta or "").strip()
    modo = str(modo or "").strip().lower()
    if not consulta:
        return ToolResult.failure(
            "A consulta de web search nao pode ser vazia.",
            error_code="empty_search_query",
            tool_name="pesquisar_web",
        )
    if modo not in MODOS:
        return ToolResult.failure(
            f"Modo de pesquisa invalido: {modo}. Use: {', '.join(MODOS)}.",
            error_code="invalid_search_mode",
            tool_name="pesquisar_web",
        )

    from providers.openai_provider import OpenAIProvider

    try:
        resposta = OpenAIProvider().search_web(
            consulta,
            mode=modo,
            mode_instruction=_MODE_INSTRUCTIONS[modo],
        )
    except Exception as erro:
        return ToolResult.failure(
            f"Nao foi possivel pesquisar na web: {erro}",
            error_code="web_search_failed",
            tool_name="pesquisar_web",
        )

    fontes = _extrair_fontes(resposta)
    if not fontes:
        texto = _texto_seguro(getattr(resposta, "output_text", ""), MAX_SNIPPET_CHARS)
        if texto:
            fontes = [{"url": "", "titulo": "", "trecho": texto}]

    total = 0
    limitadas = []
    for fonte in fontes:
        restante = MAX_TOTAL_CHARS - total
        if restante <= 0:
            break
        trecho = _texto_seguro(fonte["trecho"], min(MAX_SNIPPET_CHARS, restante))
        item = {
            "url": fonte["url"],
            "titulo": fonte["titulo"],
            "trecho": trecho,
        }
        custo = len(fonte["url"]) + len(fonte["titulo"]) + len(trecho)
        if custo > restante:
            trecho = _texto_seguro(trecho, max(1, restante - len(fonte["url"]) - len(fonte["titulo"])))
            item["trecho"] = trecho
        custo = len(item["url"]) + len(item["titulo"]) + len(item["trecho"])
        total += custo
        limitadas.append(item)

    if not limitadas:
        return ToolResult.failure(
            "A pesquisa nao retornou fontes utilizaveis.",
            error_code="web_search_no_sources",
            tool_name="pesquisar_web",
        )

    return ToolResult.success(
        f"Pesquisa web concluida em modo {modo}: {len(limitadas)} fonte(s).",
        data={
            "consulta": consulta,
            "modo": modo,
            "fontes": limitadas,
            "limite_fontes": MAX_SOURCES,
            "limite_caracteres": MAX_TOTAL_CHARS,
        },
        tool_name="pesquisar_web",
        conteudo_nao_confiavel=True,
    )
