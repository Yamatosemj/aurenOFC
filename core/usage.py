from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import date
from typing import Any, Callable

# USD por milhao de tokens, tarifa Standard, cache write de 30 minutos.
# Fontes oficiais consultadas em 2026-11-25; o identificador evita reprecificar traces antigos.
PRICE_REFERENCE = "openai-standard-2026-11-25"
MODEL_PRICES = {
    "gpt-5.6-luna": (0.20, 0.02, 0.25, 1.20),  # https://developers.openai.com/api/docs/models/gpt-5.6-luna
    "gpt-5.6-terra": (2.00, 0.20, 2.50, 12.00),  # https://developers.openai.com/api/docs/models/gpt-5.6-terra
    "gpt-5.6-sol": (4.00, 0.40, 5.00, 20.00),  # https://developers.openai.com/api/docs/models/gpt-5.6-sol
}

_model_call_observer: ContextVar[Callable[[str, float, bool, dict[str, int] | None, str | None], None] | None] = ContextVar(
    "auren_model_call_observer", default=None,
)

session_input_tokens = 0
session_output_tokens = 0
session_cached_tokens = 0
session_cache_write_tokens = 0
session_cost = 0.0  # Soma conhecida; nunca representa valor faturado.
session_cost_known_calls = 0
session_cost_unknown_calls = 0


def model_id(resposta: Any) -> str | None:
    value = getattr(resposta, "model", None)
    return value if isinstance(value, str) and value else None


def cost_status(known_calls: int, unknown_calls: int) -> str:
    if unknown_calls:
        return "partial" if known_calls else "unknown"
    return "estimated" if known_calls else "zero"


def set_model_call_observer(observer: Callable[[str, float, bool, dict[str, int] | None, str | None], None]) -> Token:
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
        observer(kind, duration_ms, success, metrics or None, model_id(response))
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


def calcular_custo_estimado(metricas: dict[str, int] | None, model: str | None = None,
                            *, on_date: date | None = None) -> float | None:
    """Retorna None sem uso/preco confiavel; zero e uma medicao valida."""
    if not isinstance(metricas, dict) or not metricas:
        return None
    entrada = max(0, int(metricas.get("input_tokens") or 0))
    saida = max(0, int(metricas.get("output_tokens") or 0))
    cache = max(0, int(metricas.get("cached_tokens") or 0))
    cache_write = max(0, int(metricas.get("cache_write_tokens") or 0))
    if cache + cache_write > entrada:
        return None
    if not (entrada or saida):
        return 0.0
    prices = MODEL_PRICES.get(model or "")
    if prices is None:
        return None
    # A tarifa promocional do Sol so esta confirmada ate esta data.
    if model == "gpt-5.6-sol" and (on_date or date.today()) > date(2026, 11, 30):
        return None
    input_rate, cached_rate, write_rate, output_rate = prices
    # A documentacao do modelo aplica 2x entrada e 1.5x saida acima de 272K.
    input_multiplier, output_multiplier = (2.0, 1.5) if entrada > 272_000 else (1.0, 1.0)
    ordinary = entrada - cache - cache_write
    return float((ordinary * input_rate + cache * cached_rate + cache_write * write_rate)
                 * input_multiplier / 1_000_000 + saida * output_rate * output_multiplier / 1_000_000)


def registrar_tentativa_sem_uso() -> None:
    global session_cost_unknown_calls
    session_cost_unknown_calls += 1


def registrar_uso(resposta):
    global session_input_tokens, session_output_tokens, session_cached_tokens
    global session_cache_write_tokens, session_cost, session_cost_known_calls

    metricas = extrair_metricas_uso(resposta)
    if not metricas:
        registrar_tentativa_sem_uso()
        return

    session_input_tokens += metricas["input_tokens"]
    session_output_tokens += metricas["output_tokens"]
    session_cached_tokens += metricas["cached_tokens"]
    session_cache_write_tokens += metricas["cache_write_tokens"]
    custo = calcular_custo_estimado(metricas, model_id(resposta))
    if custo is None:
        registrar_tentativa_sem_uso()
    else:
        session_cost += custo
        session_cost_known_calls += 1


def mostrar_uso():
    status = cost_status(session_cost_known_calls, session_cost_unknown_calls)
    amount = f"US${session_cost:.12f}" if status in {"estimated", "partial"} else (
        "US$0.000000000000" if status == "zero" else "indisponivel")
    print(
        "[sessao: "
        f"entrada={session_input_tokens}, "
        f"saida={session_output_tokens}, "
        f"cache={session_cached_tokens}, "
        f"cache_write={session_cache_write_tokens}, "
        f"custo_estimado={amount}, estado_custo={status}]"
    )
