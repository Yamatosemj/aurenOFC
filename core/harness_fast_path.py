 """Execucao do fast path do Auren sem envolver o ciclo do agente."""
from __future__ import annotations

import time
from typing import Any, Callable


def _executar_fast_path(
    mensagem: str,
    *,
    comando_rapido: Callable[[str], tuple[bool, str]],
    task_manager: Any,
    task_id: str,
    trace: Any,
    max_tool_result_chars: int,
    texto_seguro: Callable[[Any, int], str],
    registrar_turno: Callable[[str, str], Any],
    write_log: Callable[..., Any],
    resposta_wrapper: Callable[[str], Any],
) -> tuple[bool, Any] | None:
    """Executa e finaliza um comando do caminho rapido.

    Retorna None quando o comando nao foi tratado pelo fast path, deixando o
    Harness seguir para o ciclo normal do agente.
    """
    fast_started_perf = time.perf_counter()
    tratado, resposta_rapida = comando_rapido(mensagem)
    fast_path_ms = (time.perf_counter() - fast_started_perf) * 1000.0

    if trace is not None:
        try:
            trace.record_stage(
                "fast_path",
                fast_path_ms,
                category="fast_path",
                success=bool(tratado),
            )
        except Exception as exc:
            write_log("TRACE_ERROR", task_id=task_id, etapa="fast_path", erro=str(exc))

    if not tratado:
        return None

    resposta_texto = str(resposta_rapida or "").strip()
    sucesso_fast = resposta_texto and not any(
        marker in resposta_texto.lower()
        for marker in (
            "acao nao executada",
            "ação não executada",
            "nao consegui",
            "não consegui",
        )
    )

    task_manager.begin_step(
        "fast_path",
        str(mensagem or ""),
        task_id=task_id,
        step=1,
    )
    task_manager.finish_step(
        success=bool(sucesso_fast),
        result=texto_seguro(resposta_texto, max_tool_result_chars),
        error="" if sucesso_fast else texto_seguro(resposta_texto, max_tool_result_chars),
        task_id=task_id,
    )
    write_log(
        "TASK_FAST_PATH",
        task_id=task_id,
        resultado=resposta_rapida,
        sucesso=bool(sucesso_fast),
    )
    registrar_turno("assistant", resposta_texto)

    if not sucesso_fast:
        task_manager.fail("fast_path_failed", task_id=task_id)
        write_log(
            "TASK_END",
            task_id=task_id,
            status="failed",
            motivo="fast_path_failed",
        )
        return True, resposta_wrapper(resposta_texto or "Nao foi possivel concluir o comando.")

    if task_manager.should_cancel(task_id):
        task_manager.cancel(
            task_id=task_id,
            reason="cancelado antes da conclusao do fast path",
        )
        write_log(
            "TASK_END",
            task_id=task_id,
            status="cancelled",
            motivo="fast_path",
        )
        return True, resposta_wrapper("Tarefa cancelada.")

    if not resposta_texto:
        task_manager.fail("empty_response", task_id=task_id)
        write_log(
            "TASK_END",
            task_id=task_id,
            status="failed",
            motivo="empty_response",
        )
        return True, resposta_wrapper("Nao foi possivel produzir uma resposta.")

    task_manager.complete(resposta_texto, task_id=task_id)
    write_log("TASK_END", task_id=task_id, status="fast_path")
    return True, resposta_rapida
