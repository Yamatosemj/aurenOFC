from __future__ import annotations

from typing import Any, Callable


def _log_resposta_modelo(
    rodada: int,
    resposta: Any,
    latencia_ms: float,
    metricas_roteamento: dict[str, Any],
    *,
    trace: Any,
    task_id: str,
    uso_resposta: Callable[[Any], Any],
    write_log: Callable[..., Any],
    **extra: Any,
) -> None:
    """Registra trace e resposta de uma rodada do modelo sem alterar o fluxo."""
    if trace is not None:
        try:
            trace.record_model(
                rodada,
                latencia_ms,
                uso_resposta(resposta),
            )
        except Exception as exc:
            write_log("TRACE_ERROR", task_id=task_id, etapa="model", erro=str(exc))
    write_log(
        "MODEL_ROUND_RESPONSE",
        task_id=task_id,
        rodada=rodada,
        output_items=len(getattr(resposta, "output", []) or []),
        output_text=getattr(resposta, "output_text", "") or "",
        uso=uso_resposta(resposta),
        latencia_ms=round(latencia_ms, 3),
        router=metricas_roteamento,
        **extra,
    )
