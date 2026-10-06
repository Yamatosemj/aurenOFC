from __future__ import annotations

from typing import Any, Callable


def _salvar_estrategia_em_background(
    objetivo: str,
    historico: list[dict[str, str]],
    resultado: str,
    sucesso: bool = True,
    *,
    context: Any,
    background_queue: Any,
    task_id: str,
    chat_id: str | None,
    write_log: Callable[..., None],
) -> None:
    """Persiste a estratégia sem bloquear o caminho crítico da resposta."""
    if not context.persiste or not historico:
        return

    passos = [
        f"{h.get('ferramenta', '')}: {h.get('resultado', '')[:240]}"
        for h in historico
    ]

    def _runner(cancel_event):
        if cancel_event.is_set():
            return {"ok": False, "cancelado": True}
        return context.record_strategy(
            objetivo,
            passos,
            resultado,
            sucesso,
            chat_id=chat_id,
        )

    try:
        background_task_id = background_queue.submit(
            f"salvar estrategia: {objetivo[:120]}",
            _runner,
            priority=100,
        )
        write_log(
            "BACKGROUND_TASK_QUEUED",
            task_id=task_id,
            background_task_id=background_task_id,
            tipo="salvar_estrategia",
        )
    except Exception as exc:
        # A fila é otimização; em falha de infraestrutura fazemos fallback síncrono.
        try:
            context.record_strategy(
                objetivo,
                passos,
                resultado,
                sucesso,
                chat_id=chat_id,
            )
        except Exception as fallback_exc:
            write_log(
                "MEMORY_ERROR",
                task_id=task_id,
                erro=f"estrategia: {fallback_exc}",
                fila_erro=str(exc),
            )
