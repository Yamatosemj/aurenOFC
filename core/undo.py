"""Pilha thread-safe de acoes reversiveis do Auren.

A pilha guarda somente operacoes cujo estado anterior foi observado antes da
mudanca. A execucao do desfazer permanece separada da selecao de ferramentas:
a tool publica pede o undo, e o callback apenas aplica a reversao capturada.

Cada entrada tem rotulo e horario UTC; a profundidade maxima e 10 e entradas
antigas sao descartadas quando uma nova excede o limite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Callable

from core.tool_result import ToolResult


MAX_DEPTH = 10


@dataclass(frozen=True)
class UndoEntry:
    """Registra uma acao reversivel com seu estado executavel de reversao.
    O objeto mantem o rotulo, o callback e o instante observado pela pilha.
    Custo: O(1) para armazenar a entrada, alem da memoria capturada pelo callback.
    """

    label: str
    undo: Callable[[], Any]
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class UndoOutcome:
    """Descreve o resultado de uma tentativa de desfazer uma entrada.
    O status distingue sucesso, pilha vazia e falha sem apagar a entrada.
    Custo: O(1) para construir o resultado, sem executar nova acao.
    """

    status: str
    label: str = ""
    at: datetime | None = None
    detail: str = ""
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        """Informa se a reversao foi concluida com sucesso.
        O status e produzido pela pilha depois do callback terminar.
        Custo: O(1).
        """
        return self.status == "undone"


_stack: list[UndoEntry] = []
_lock = threading.RLock()


def push_undo(label: str, undo_fn: Callable[[], Any]) -> None:
    """Registra uma acao e o callback que restaura seu estado anterior.
    A entrada e protegida por lock e limitada a MAX_DEPTH.
    Custo: O(1) amortizado, fora a captura de estado feita pelo callback.
    """
    if not callable(undo_fn):
        return
    try:
        with _lock:
            _stack.append(UndoEntry(label=str(label)[:120], undo=undo_fn))
            if len(_stack) > MAX_DEPTH:
                del _stack[:-MAX_DEPTH]
    except Exception:
        return


def can_undo() -> bool:
    """Informa se existe uma acao reversivel pronta para desfazer.
    Consulta a pilha sob lock sem executar callbacks.
    Custo: O(1).
    """
    with _lock:
        return bool(_stack)


def peek() -> str:
    """Retorna o rotulo da proxima acao reversivel sem remove-la.
    A leitura e feita de forma atomica sob lock.
    Custo: O(1).
    """
    with _lock:
        return _stack[-1].label if _stack else ""


def history() -> list[str]:
    """Retorna os rotulos mais recentes primeiro para consulta do historico.
    Nenhum callback e executado durante a leitura.
    Custo: O(n), com n limitado a MAX_DEPTH.
    """
    with _lock:
        return [entry.label for entry in reversed(_stack)]


def _interpretar_retorno(resultado: Any) -> tuple[bool, str, str | None]:
    if isinstance(resultado, ToolResult):
        return resultado.ok, resultado.message, resultado.error_code
    if resultado is False:
        return False, "O callback de undo informou falha.", "undo_callback_failed"
    if resultado is None or resultado is True:
        return True, "", None
    return True, str(resultado), None


def undo_last() -> UndoOutcome:
    """Desfaz a ultima acao reversivel sem perder a entrada quando falha.
    O callback roda sob RLock e a entrada so sai apos sucesso confirmado.
    Custo: O(1) de pilha mais o custo real da reversao solicitada.
    """
    with _lock:
        if not _stack:
            return UndoOutcome(status="empty")

        entry = _stack[-1]
        try:
            resultado = entry.undo()
            ok, detail, error_code = _interpretar_retorno(resultado)
        except Exception as exc:
            return UndoOutcome(
                status="failed",
                label=entry.label,
                at=entry.at,
                detail=str(exc),
                error_code="undo_exception",
            )

        if not ok:
            return UndoOutcome(
                status="failed",
                label=entry.label,
                at=entry.at,
                detail=detail,
                error_code=error_code or "undo_failed",
            )

        for indice in range(len(_stack) - 1, -1, -1):
            if _stack[indice] is entry:
                del _stack[indice]
                break

        return UndoOutcome(
            status="undone",
            label=entry.label,
            at=entry.at,
            detail=detail,
        )


def clear() -> None:
    """Esvazia a pilha para iniciar uma sessao limpa ou liberar callbacks.
    A operacao e protegida por lock e nao executa nenhum undo pendente.
    Custo: O(n), com n limitado a MAX_DEPTH.
    """
    with _lock:
        _stack.clear()
