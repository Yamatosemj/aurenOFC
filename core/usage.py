from __future__ import annotations

import json
import math
import os
from typing import Any

from config import MODEL

session_input_tokens = 0
session_output_tokens = 0
session_cached_tokens = 0
session_cache_write_tokens = 0
session_cost = 0.0
session_cost_reference_only = False


def _tarifa_modelo(modelo: str | None = None) -> dict[str, float] | None:
    try:
        prices = json.loads(os.getenv("AUREN_MODEL_PRICES_JSON", "{}"))
        raw = prices.get(modelo or MODEL)
        if not isinstance(raw, dict):
            return None
        rates = {name: float(raw[name]) for name in ("input", "cached", "cache_write", "output")}
        if any(not math.isfinite(value) or value < 0 for value in rates.values()):
            return None
        return rates
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def base_do_custo(modelo: str | None = None) -> str:
    return "tarifa_configurada" if _tarifa_modelo(modelo) is not None else "referencia_generica_nao_fatura"



def extrair_metricas_uso(resposta) -> dict[str, Any]:
    uso = getattr(resposta, "usage", None)
    if uso is None:
        return {}

    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    saida = int(getattr(uso, "output_tokens", 0) or 0)
    detalhes = getattr(uso, "input_tokens_details", None)
    cache = int(getattr(detalhes, "cached_tokens", 0) or 0) if detalhes else 0
    cache_write = int(getattr(detalhes, "cache_write_tokens", 0) or 0) if detalhes else 0
    metrics = {
        "input_tokens": max(0, entrada),
        "output_tokens": max(0, saida),
        "cached_tokens": max(0, cache),
        "cache_write_tokens": max(0, cache_write),
    }
    model = getattr(resposta, "model", None)
    if isinstance(model, str) and model.strip():
        metrics["model"] = model.strip()
    return metrics


def calcular_custo_estimado(metricas: dict[str, Any] | None, *, modelo: str | None = None) -> float:
    valores = metricas if isinstance(metricas, dict) else {}
    entrada = max(0, int(valores.get("input_tokens") or 0))
    saida = max(0, int(valores.get("output_tokens") or 0))
    cache = max(0, int(valores.get("cached_tokens") or 0))
    cache_write = max(0, int(valores.get("cache_write_tokens") or 0))
    entrada_sem_cache = max(0, entrada - cache - cache_write)
    rates = _tarifa_modelo(modelo or valores.get("model")) or {
        "input": 0.20, "cached": 0.02, "cache_write": 0.25, "output": 1.20}
    custo = entrada_sem_cache * rates["input"] / 1_000_000
    custo += cache * rates["cached"] / 1_000_000
    custo += cache_write * rates["cache_write"] / 1_000_000
    custo += saida * rates["output"] / 1_000_000
    return float(custo)
def registrar_uso(resposta):
    global session_input_tokens
    global session_output_tokens
    global session_cached_tokens
    global session_cache_write_tokens
    global session_cost
    global session_cost_reference_only

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
    session_cost_reference_only = session_cost_reference_only or _tarifa_modelo(metricas.get("model")) is None

def mostrar_uso():
    label = "referencia_generica_nao_fatura" if session_cost_reference_only else "custo_estimado"
    print(
        "[processo: "
        f"entrada={session_input_tokens}, "
        f"saida={session_output_tokens}, "
        f"cache={session_cached_tokens}, "
        f"cache_write={session_cache_write_tokens}, "
        f"{label}=US${session_cost:.6f}]"
    )
