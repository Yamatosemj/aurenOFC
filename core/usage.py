from __future__ import annotations

session_input_tokens = 0
session_output_tokens = 0
session_cached_tokens = 0
session_cache_write_tokens = 0
session_cost = 0.0


def registrar_uso(resposta):
    global session_input_tokens
    global session_output_tokens
    global session_cached_tokens
    global session_cache_write_tokens
    global session_cost

    uso = getattr(
        resposta,
        "usage",
        None
    )

    if uso is None:
        return

    entrada = getattr(
        uso,
        "input_tokens",
        0
    )

    saida = getattr(
        uso,
        "output_tokens",
        0
    )

    detalhes = getattr(
        uso,
        "input_tokens_details",
        None
    )

    cache = 0
    cache_write = 0

    if detalhes is not None:
        cache = getattr(
            detalhes,
            "cached_tokens",
            0
        )

        cache_write = getattr(
            detalhes,
            "cache_write_tokens",
            0
        )

    entrada_sem_cache = max(
        0,
        entrada - cache - cache_write
    )

    custo = (
        entrada_sem_cache
        * 0.20
        / 1_000_000
    )

    custo += (
        cache
        * 0.02
        / 1_000_000
    )

    custo += (
        cache_write
        * 0.25
        / 1_000_000
    )

    custo += (
        saida
        * 1.20
        / 1_000_000
    )

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
