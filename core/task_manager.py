from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Any
import uuid


class TaskState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}

_ALLOWED_TRANSITIONS = {
    TaskState.CREATED: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.RUNNING: {
        TaskState.WAITING,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING: {
        TaskState.RUNNING,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


@dataclass(frozen=True)
class TaskStep:
    step: int
    tool: str
    arguments: str = ""
    attempt: int = 1
    started_at: str = ""
    finished_at: str = ""
    success: bool | None = None
    result: str = ""
    error: str = ""


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    objective: str
    state: TaskState
    chat_id: str | None
    created_at: str
    started_at: str
    finished_at: str
    current_step: int
    current_tool: str | None
    attempts: int
    cancel_requested: bool
    result: str
    error: str
    steps: tuple[TaskStep, ...]


@dataclass
class _TaskRecord:
    task_id: str
    objective: str
    chat_id: str | None
    created_at: str
    state: TaskState = TaskState.CREATED
    started_at: str = ""
    finished_at: str = ""
    current_step: int = 0
    current_tool: str | None = None
    attempts: int = 0
    cancel_requested: bool = False
    result: str = ""
    error: str = ""
    steps: list[TaskStep] = field(default_factory=list)


class TaskManager:
    """Mantem o ciclo de vida operacional das tarefas do Auren.

    Esta primeira versao e deliberadamente em memoria. Ela nao agenda tarefas,
    nao cria novas ferramentas e nao altera permissoes. Seu papel e dar ao Core
    uma fonte unica de verdade sobre a tarefa atual.
    """

    def __init__(self, *, max_history: int = 100) -> None:
        if max_history < 1:
            raise ValueError("max_history deve ser maior que zero.")
        self.max_history = max_history
        self._tasks: dict[str, _TaskRecord] = {}
        self._current_task_id: str | None = None
        self._lock = RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _new_task_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6]

    def create(self, objective: str, *, chat_id: str | None = None, task_id: str | None = None) -> TaskSnapshot:
        """Cria e seleciona uma nova tarefa no estado CREATED."""
        with self._lock:
            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current is not None and current.state not in _TERMINAL_STATES:
                    raise RuntimeError(
                        f"Ja existe uma tarefa ativa: {current.task_id} ({current.state.value})."
                    )

            new_id = task_id or self._new_task_id()
            if new_id in self._tasks:
                raise ValueError(f"task_id ja existe: {new_id}")

            record = _TaskRecord(
                task_id=new_id,
                objective=str(objective or "").strip(),
                chat_id=chat_id,
                created_at=self._now(),
            )
            self._tasks[new_id] = record
            self._current_task_id = new_id
            self._prune_history()
            return self.snapshot(new_id)

    def _require(self, task_id: str | None = None) -> _TaskRecord:
        selected = task_id or self._current_task_id
        if not selected or selected not in self._tasks:
            raise RuntimeError("Nenhuma tarefa selecionada.")
        return self._tasks[selected]

    def _transition(self, record: _TaskRecord, state: TaskState) -> None:
        if record.state == state:
            return
        if state not in _ALLOWED_TRANSITIONS[record.state]:
            raise RuntimeError(
                f"Transicao invalida para tarefa {record.task_id}: "
                f"{record.state.value} -> {state.value}"
            )
        record.state = state

    def _ensure_not_terminal(self, record: _TaskRecord, operation: str) -> None:
        if record.state in _TERMINAL_STATES:
            raise RuntimeError(
                f"Nao e possivel {operation} em tarefa terminal {record.task_id} ({record.state.value})."
            )

    def _cancel_locked(self, record: _TaskRecord, reason: str) -> None:
        self._transition(record, TaskState.CANCELLED)
        record.cancel_requested = True
        record.error = str(reason or "cancelado")
        record.finished_at = self._now()

    def start(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._transition(record, TaskState.RUNNING)
            if not record.started_at:
                record.started_at = self._now()
            return self.snapshot(record.task_id)

    def wait_for_model(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._transition(record, TaskState.WAITING)
            return self.snapshot(record.task_id)

    def resume(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._transition(record, TaskState.RUNNING)
            return self.snapshot(record.task_id)

    def begin_step(
        self,
        tool: str,
        arguments: str = "",
        *,
        task_id: str | None = None,
        step: int | None = None,
    ) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            if record.state == TaskState.WAITING:
                self._transition(record, TaskState.RUNNING)
            elif record.state != TaskState.RUNNING:
                raise RuntimeError(
                    f"Nao e possivel iniciar passo em estado {record.state.value}."
                )

            record.current_step = step if step is not None else record.current_step + 1
            record.current_tool = str(tool or "") or None
            record.attempts += 1
            record.steps.append(
                TaskStep(
                    step=record.current_step,
                    tool=record.current_tool or "",
                    arguments=str(arguments or ""),
                    attempt=record.attempts,
                    started_at=self._now(),
                )
            )
            return self.snapshot(record.task_id)

    def finish_step(
        self,
        *,
        success: bool,
        result: str = "",
        error: str = "",
        task_id: str | None = None,
    ) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "finalizar passo")
            if not record.steps:
                raise RuntimeError("Nenhum passo ativo para finalizar.")

            previous = record.steps[-1]
            record.steps[-1] = TaskStep(
                step=previous.step,
                tool=previous.tool,
                arguments=previous.arguments,
                attempt=previous.attempt,
                started_at=previous.started_at,
                finished_at=self._now(),
                success=bool(success),
                result=str(result or ""),
                error=str(error or ""),
            )
            record.current_tool = previous.tool
            return self.snapshot(record.task_id)

    def complete(self, result: str = "", *, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "concluir")
            if record.cancel_requested:
                self._cancel_locked(record, "cancelado antes da conclusao")
                return self.snapshot(record.task_id)
            self._transition(record, TaskState.COMPLETED)
            record.result = str(result or "")
            record.finished_at = self._now()
            return self.snapshot(record.task_id)

    def fail(self, error: str, *, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "falhar")
            if record.cancel_requested:
                self._cancel_locked(record, "cancelado antes da falha")
                return self.snapshot(record.task_id)
            self._transition(record, TaskState.FAILED)
            record.error = str(error or "")
            record.finished_at = self._now()
            return self.snapshot(record.task_id)

    def request_cancel(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "solicitar cancelamento")
            record.cancel_requested = True
            return self.snapshot(record.task_id)

    def cancel(self, *, task_id: str | None = None, reason: str = "cancelado pelo usuario") -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "cancelar")
            self._cancel_locked(record, reason)
            return self.snapshot(record.task_id)

    def should_cancel(self, task_id: str | None = None) -> bool:
        with self._lock:
            return bool(self._require(task_id).cancel_requested)

    def current_snapshot(self) -> TaskSnapshot | None:
        with self._lock:
            if not self._current_task_id:
                return None
            return self.snapshot(self._current_task_id)

    def get_snapshot(self, task_id: str) -> TaskSnapshot:
        with self._lock:
            return self.snapshot(task_id)

    def snapshot(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            return TaskSnapshot(
                task_id=record.task_id,
                objective=record.objective,
                state=record.state,
                chat_id=record.chat_id,
                created_at=record.created_at,
                started_at=record.started_at,
                finished_at=record.finished_at,
                current_step=record.current_step,
                current_tool=record.current_tool,
                attempts=record.attempts,
                cancel_requested=record.cancel_requested,
                result=record.result,
                error=record.error,
                steps=tuple(record.steps),
            )

    def recent_snapshots(
        self,
        chat_id: str | None,
        *,
        limit: int = 3,
        terminal_only: bool = True,
    ) -> tuple[TaskSnapshot, ...]:
        """Ultimas tarefas de UM chat (ordem cronologica), somente leitura.

        Sem chat_id retorna vazio: nunca mistura tarefas de chats diferentes.
        """
        if not chat_id or limit < 1:
            return ()
        with self._lock:
            ids = [
                record.task_id
                for record in self._tasks.values()  # dict preserva ordem de criacao
                if record.chat_id == chat_id
                and (not terminal_only or record.state in _TERMINAL_STATES)
            ]
            return tuple(self.snapshot(task_id) for task_id in ids[-limit:])

    def clear_current(self) -> None:
        with self._lock:
            self._current_task_id = None

    def _prune_history(self) -> None:
        if len(self._tasks) <= self.max_history:
            return
        ordered = sorted(
            self._tasks.values(),
            key=lambda item: item.created_at,
        )
        protected = {self._current_task_id}
        for record in ordered:
            if len(self._tasks) <= self.max_history:
                break
            if record.task_id in protected:
                continue
            if record.state in _TERMINAL_STATES:
                self._tasks.pop(record.task_id, None)


__all__ = [
    "TaskManager",
    "TaskSnapshot",
    "TaskState",
    "TaskStep",
]
