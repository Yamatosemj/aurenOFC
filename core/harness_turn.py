from __future__ import annotations

from typing import Any, Callable


def _registrar_turno(
    papel: str,
    texto: str,
    *,
    context: Any,
    chat_id: str,
    task_id: str,
    write_log: Callable[..., None],
) -> None:
    """Grava um turno no Context do chat atual sem derrubar a tarefa."""
    if not context.persiste or not str(texto or "").strip():
        return

    try:
        context.record_turn(chat_id, papel, str(texto))
    except Exception as exc:
        write_log(
            "MEMORY_ERROR",
            task_id=task_id,
            erro=f"historico_{papel}: {exc}",
        )
