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


def _executar_rodada_modelo(
    entrada: Any,
    *,
    rodada: int,
    task_id: str,
    task_manager: Any,
    pedir_modelo: Callable[
        [Any, str | None],
        tuple[Any, float, dict[str, Any]] | None,
    ],
    log_resposta_modelo: Callable[..., Any],
    write_log: Callable[..., Any],
    input_items: int,
    estado_chars: int,
    tool_choice: str | None = None,
    log_tool_choice: str | None = None,
) -> tuple[Any, float, dict[str, Any]] | None:
    """Executa a mecânica completa de uma rodada do modelo.

    O Harness continua decidindo quando a rodada deve acontecer e qual input
    enviar. Este helper só preserva a sequência operacional:
    espera -> log da requisição -> chamada -> log da resposta -> retomada.
    """
    task_manager.wait_for_model(task_id)

    detalhes = {
        "task_id": task_id,
        "rodada": rodada,
        "input_items": input_items,
        "estado_chars": estado_chars,
    }
    if log_tool_choice is not None:
        detalhes["tool_choice"] = log_tool_choice
    write_log("MODEL_ROUND_REQUEST", **detalhes)

    chamada = pedir_modelo(entrada, tool_choice)
    if chamada is None:
        return None

    resposta, latencia_ms, metricas_roteamento = chamada
    log_resposta_modelo(
        rodada,
        resposta,
        latencia_ms,
        metricas_roteamento,
    )
    task_manager.resume(task_id)
    return resposta, latencia_ms, metricas_roteamento
