from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Callable

_model_call_observer: ContextVar[Callable[[str, float, bool, dict[str, int] | None], None] | None] = ContextVar(
    "auren_model_call_observer", default=None,
)

session_input_tokens = 0
session_output_tokens = 0
session_cached_tokens = 0
session_cache_write_tokens = 0
session_cost = 0.0


def set_model_call_observer(observer: Callable[[str, float, bool, dict[str, int] | None], None]) -> Token:
    return _model_call_observer.set(observer)


def reset_model_call_observer(token: Token) -> None:
    _model_call_observer.reset(token)


def observe_provider_call(kind: str, duration_ms: float, *, response: Any = None, success: bool) -> None:
    """Notifica o trace da tarefa; falhas da telemetria nao afetam o provider."""
    observer = _model_call_observer.get()
    if observer is None:
        return
    try:
        metrics = extrair_metricas_uso(response) if success else {}
        observer(kind, duration_ms, success, metrics or None)
    except Exception:
        pass


def extrair_metricas_uso(resposta) -> dict[str, int]:
    uso = getattr(resposta, "usage", None)
    if uso is None:
        return {}

    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    saida = int(getattr(uso, "output_tokens", 0) or 0)
    detalhes = getattr(uso, "input_tokens_details", None)
    cache = int(getattr(detalhes, "cached_tokens", 0) or 0) if detalhes else 0
    cache_write = int(getattr(detalhes, "cache_write_tokens", 0) or 0) if detalhes else 0
    return {
        "input_tokens": max(0, entrada),
        "output_tokens": max(0, saida),
        "cached_tokens": max(0, cache),
        "cache_write_tokens": max(0, cache_write),
    }


def calcular_custo_estimado(metricas: dict[str, int] | None) -> float:
    valores = metricas if isinstance(metricas, dict) else {}
    entrada = max(0, int(valores.get("input_tokens") or 0))
    saida = max(0, int(valores.get("output_tokens") or 0))
    cache = max(0, int(valores.get("cached_tokens") or 0))
    cache_write = max(0, int(valores.get("cache_write_tokens") or 0))
    entrada_sem_cache = max(0, entrada - cache - cache_write)
    custo = entrada_sem_cache * 0.20 / 1_000_000
    custo += cache * 0.02 / 1_000_000
    custo += cache_write * 0.25 / 1_000_000
    custo += saida * 1.20 / 1_000_000
    return float(custo)
def registrar_uso(resposta):
    global session_input_tokens
    global session_output_tokens
    global session_cached_tokens
    global session_cache_write_tokens
    global session_cost

    metricas = extrair_metricas_uso(resposta)

    if not metricas:
        return

    entrada = metricas["input_tokens"]
    saida = metricas["output_tokens"]
    cache = metricas["cached_tokens"]
    cache_write = metricas["cache_write_tokens"]
    custo = calcular_custo_estimado(metricas)

    session_input_tokens += entrada
    session_output_tokens += saida
    session_cached_tokens += cache
    session_cache_write_tokens += cache_write
    session_cost += custo

def mostrar_uso():
    print(
        "[sessao: "
        f"entrada={session_input_tokens}, "
        f"saida={session_output_tokens}, "
        f"cache={session_cached_tokens}, "
        f"cache_write={session_cache_write_tokens}, "
        f"custo_estimado=US${session_cost:.6f}]"
    )
