from __future__ import annotations

from typing import Any

from core.orchestrator import AurenOrchestrator
from core.tools_registry import tools as TOOL_REGISTRY


_orchestrator = AurenOrchestrator()


def get_client():
    """Compatibilidade: o cliente continua disponivel para codigo legado."""
    return _orchestrator.get_client()


def criar_resposta(
    entrada: Any,
    response_id: str | None = None,
    reasoning_effort: str = "none",
    tool_choice: str | dict | None = None,
):
    """Compatibilidade da V43 usando a nova cadeia Orchestrator -> Brain -> Provider."""
    return _orchestrator.create_response(
        entrada,
        response_id=response_id,
        reasoning_effort=reasoning_effort,
        tool_choice=tool_choice,
    )


def obter_metricas_roteamento() -> dict[str, object]:
    """Retorna um snapshot observacional da ultima selecao do Router."""
    router = _orchestrator.router
    cache = _orchestrator.get_response_cache_stats()
    return {
        "dominios": list(router.last_domains),
        "ferramentas": len(router.last_tool_names),
        "fallback_45": len(router.last_tool_names) == len(TOOL_REGISTRY),
        "response_cache_hits": cache.get("hits", 0),
        "response_cache_misses": cache.get("misses", 0),
        "response_cache_items": cache.get("itens", 0),
    }
