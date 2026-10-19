from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Any
import uuid
import re
from functools import wraps

from agent.models import ExecutionPlan, PlanStep


def _persistent_change(method):
    @wraps(method)
    def apply(self, *args, **kwargs):
        with self._lock:
            if self._closed:
                raise RuntimeError('Manager de tarefas encerrado.')
            if self._storage is None:
                return method(self, *args, **kwargs)
            if self._transaction_before is not None:
                return method(self, *args, **kwargs)
            # Clone records lazily in _require, before mutation. Historical
            # tasks are unchanged; serializing/copying all of them per model
            # transition made each ordinary turn grow with the chat history.
            before, selected = dict(self._tasks), self._current_task_id
            self._transaction_before = before
            try:
                result = method(self, *args, **kwargs)
                changed = {key: value for key, value in self._tasks.items() if before.get(key) is not value}
                records = {key: asdict(value) for key, value in changed.items()}
                previous = {key:asdict(before[key]) for key in changed if key in before}
                for key, value in records.items():
                    if value != previous.get(key):
                        self._decode_record(value)
                self._storage.save(records, self._current_task_id, method.__name__, previous)
                return result
            except BaseException:
                self._tasks, self._current_task_id = before, selected
                raise
            finally:
                self._transaction_before = None
    return apply


class TaskState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}

_ALLOWED_TRANSITIONS = {
    TaskState.CREATED: {TaskState.RUNNING, TaskState.PAUSED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.RUNNING: {
        TaskState.WAITING,
        TaskState.PAUSED,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING: {
        TaskState.RUNNING,
        TaskState.PAUSED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.PAUSED: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.INTERRUPTED: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
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
    signature: str = ""


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
    plan: ExecutionPlan | None = None
    model_calls: int = 0
    model_limit: int = 0
    checkpoint_steps: int = -1
    permission_limits: dict | None = None


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
    plan: ExecutionPlan | None = None
    model_calls: int = 0
    model_limit: int = 0
    checkpoint_steps: int = -1
    permission_limits: dict | None = None


class TaskManager:
    """Mantem o ciclo de vida operacional das tarefas do Auren.

    Em memoria por padrao; db_path habilita checkpoints e historico em SQLite.
    Nao agenda, autoriza ou executa ferramentas. Estados recuperados nao
    restauram permissoes e passos incertos nao podem ser retomados cegamente.
    """

    def __init__(self, *, max_history: int = 100, db_path=None) -> None:
        if max_history < 1:
            raise ValueError("max_history deve ser maior que zero.")
        self.max_history = max_history
        self._tasks: dict[str, _TaskRecord] = {}
        self._current_task_id: str | None = None
        self._lock = RLock()
        self._closed = False
        self._storage = None
        self._transaction_before = None
        if db_path is not None:
            from core.task_persistence import TaskStorage
            self._storage = TaskStorage(db_path)
            try:
                records, self._current_task_id = self._storage.load(max_history)
                self._tasks = {key:self._decode_record(value) for key,value in records.items()}
                if any(key != record.task_id for key,record in self._tasks.items()):
                    raise RuntimeError('Identidade da tarefa diverge do checkpoint.')
                if self._current_task_id is not None and self._current_task_id not in self._tasks:
                    raise RuntimeError('Checkpoint referencia tarefa ausente.')
                before = self._records()
                for record in self._tasks.values():
                    if record.state in {TaskState.CREATED, TaskState.RUNNING, TaskState.WAITING}:
                        record.state = TaskState.INTERRUPTED
                self._storage.save(self._records(), self._current_task_id, 'recover', before)
            except BaseException:
                self._storage.close()
                raise

    @property
    def persistent(self):
        return self._storage is not None

    @property
    def closed(self):
        return self._closed

    @staticmethod
    def _decode_record(value):
        data = dict(value)
        data['state'] = TaskState(data['state'])
        data['steps'] = [TaskStep(**step) for step in data['steps']]
        if data.get('plan') is not None:
            plan = dict(data['plan'])
            plan['steps'] = tuple(PlanStep(**step) for step in plan['steps'])
            data['plan'] = ExecutionPlan(**plan)
        record = _TaskRecord(**data)
        if (any(type(v) is not int or v < 0 for v in (record.model_calls, record.model_limit))
                or record.model_calls > record.model_limit
                or type(record.checkpoint_steps) is not int
                or not -1 <= record.checkpoint_steps <= len(record.steps)):
            raise RuntimeError('Checkpoint de orcamento invalido.')
        if record.permission_limits is not None:
            from core.permission_manager import PermissionManager
            PermissionManager().restore_limits(record.permission_limits)
        if (type(record.cancel_requested) is not bool
                or not all(isinstance(getattr(record, key), str) for key in
                           ('task_id', 'objective', 'created_at', 'started_at', 'finished_at', 'result', 'error'))
                or not record.task_id
                or (record.chat_id is not None and not isinstance(record.chat_id, str))
                or (record.current_tool is not None and not isinstance(record.current_tool, str))
                or any(type(value) is not int or value < 0 for value in (record.current_step, record.attempts))):
            raise RuntimeError('Checkpoint de tarefa possui tipos invalidos.')
        for step in record.steps:
            if (type(step.success) not in {bool, type(None)}
                    or not isinstance(step.signature, str)
                    or (step.signature and not re.fullmatch(r'[0-9a-f]{64}', step.signature))
                    or not all(isinstance(getattr(step, key), str) for key in
                               ('tool', 'arguments', 'started_at', 'finished_at', 'result', 'error'))
                    or type(step.step) is not int or step.step < 0
                    or type(step.attempt) is not int or step.attempt < 1
                    or ((step.success is not None) != bool(step.finished_at))):
                raise RuntimeError('Checkpoint de passo possui resultado invalido.')
        if record.plan is not None:
            plan = record.plan
            if (not isinstance(plan.objective, str) or not isinstance(plan.complexity, str)
                    or type(plan.max_rounds) is not int or plan.max_rounds < 1
                    or any(type(step.index) is not int or step.index < 1
                           or not isinstance(step.instruction, str)
                           or (step.expected_domain is not None and not isinstance(step.expected_domain, str))
                           for step in plan.steps)):
                raise RuntimeError('Checkpoint de plano possui tipos invalidos.')
        return record

    def _records(self):
        return {key:asdict(record) for key,record in self._tasks.items()}

    def close(self):
        with self._lock:
            self._closed = True
            if self._storage is not None:
                self._storage.close()

    def execution_history(self, task_id, *, after_sequence=0, limit=100):
        with self._lock:
            if self._storage is None or self._closed:
                raise RuntimeError('Historico persistente indisponivel.')
            return self._storage.history(task_id, after_sequence=after_sequence, limit=limit)

    def list_snapshots(self, chat_id, *, limit=100, offset=0):
        """Lista tambem objetivos arquivados, mais recentes primeiro, por chat."""
        if not chat_id:
            return ()
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise ValueError('Paginacao de tarefas invalida.')
        with self._lock:
            if self._closed:
                raise RuntimeError('Manager de tarefas encerrado.')
            if self._storage is not None:
                ids = self._storage.list_ids(chat_id, limit, offset)
            else:
                ids = [r.task_id for r in reversed(tuple(self._tasks.values())) if r.chat_id == chat_id]
                ids = ids[offset:offset + limit]
            return tuple(self.snapshot(task_id) for task_id in ids)

    def list_chat_ids(self):
        with self._lock:
            if self._closed:
                raise RuntimeError('Manager encerrado.')
            return (self._storage.list_chat_ids() if self._storage is not None else
                    tuple(sorted({r.chat_id for r in self._tasks.values() if r.chat_id})))

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _new_task_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6]

    @_persistent_change
    def create(self, objective: str, *, chat_id: str | None = None, task_id: str | None = None,
               plan: ExecutionPlan | None = None) -> TaskSnapshot:
        """Cria e seleciona uma nova tarefa no estado CREATED."""
        with self._lock:
            if plan is not None and not isinstance(plan, ExecutionPlan):
                raise ValueError('Plano precisa ser um ExecutionPlan.')
            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current is not None and current.state not in _TERMINAL_STATES:
                    raise RuntimeError(
                        f"Ja existe uma tarefa ativa: {current.task_id} ({current.state.value})."
                    )

            new_id = task_id or self._new_task_id()
            if new_id in self._tasks or (self._storage is not None and self._storage.get(new_id) is not None):
                raise ValueError(f"task_id ja existe: {new_id}")

            record = _TaskRecord(
                task_id=new_id,
                objective=str(objective or "").strip(),
                chat_id=chat_id,
                created_at=self._now(),
                plan=plan,
            )
            self._tasks[new_id] = record
            self._current_task_id = new_id
            self._prune_history()
            return self.snapshot(new_id)

    def _require(self, task_id: str | None = None) -> _TaskRecord:
        selected = task_id or self._current_task_id
        if selected and selected not in self._tasks and self._storage is not None and not self._closed:
            archived = self._storage.get(selected)
            if archived is not None:
                record = self._decode_record(archived)
                if record.task_id != selected:
                    raise RuntimeError('Identidade da tarefa diverge do checkpoint.')
                self._tasks[selected] = record
        if not selected or selected not in self._tasks:
            raise RuntimeError("Nenhuma tarefa selecionada.")
        before = self._transaction_before
        if before is not None and selected in before and self._tasks[selected] is before[selected]:
            self._tasks[selected] = deepcopy(before[selected])
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

    @_persistent_change
    def start(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            if record.state in {TaskState.PAUSED, TaskState.INTERRUPTED}:
                raise RuntimeError('Use resume_checkpoint para retomar com verificacao de incerteza.')
            self._transition(record, TaskState.RUNNING)
            if not record.started_at:
                record.started_at = self._now()
            return self.snapshot(record.task_id)

    @_persistent_change
    def wait_for_model(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._transition(record, TaskState.WAITING)
            return self.snapshot(record.task_id)

    @_persistent_change
    def resume(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            if record.state in {TaskState.PAUSED, TaskState.INTERRUPTED}:
                raise RuntimeError('Use resume_checkpoint para retomar com verificacao de incerteza.')
            self._transition(record, TaskState.RUNNING)
            return self.snapshot(record.task_id)

    @_persistent_change
    def begin_step(
        self,
        tool: str,
        arguments: str = "",
        *,
        task_id: str | None = None,
        step: int | None = None,
        signature: str = '',
    ) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            if record.steps and record.steps[-1].success is None:
                raise RuntimeError('Existe um passo incerto sem resultado confirmado.')
            if record.state == TaskState.WAITING:
                self._transition(record, TaskState.RUNNING)
            elif record.state != TaskState.RUNNING:
                raise RuntimeError(
                    f"Nao e possivel iniciar passo em estado {record.state.value}."
                )

            record.current_step = step if step is not None else record.current_step + 1
            record.checkpoint_steps = -1
            record.current_tool = str(tool or "") or None
            record.attempts += 1
            record.steps.append(
                TaskStep(
                    step=record.current_step,
                    tool=record.current_tool or "",
                    arguments=str(arguments or ""),
                    attempt=record.attempts,
                    started_at=self._now(),
                    signature=signature,
                )
            )
            return self.snapshot(record.task_id)

    @_persistent_change
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
            if record.state not in {TaskState.RUNNING, TaskState.WAITING} or previous.success is not None:
                raise RuntimeError('Nao existe passo em execucao para receber um resultado.')
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
                signature=previous.signature,
            )
            record.current_tool = previous.tool
            return self.snapshot(record.task_id)

    @_persistent_change
    def complete(self, result: str = "", *, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "concluir")
            if record.cancel_requested:
                self._cancel_locked(record, "cancelado antes da conclusao")
                return self.snapshot(record.task_id)
            if record.steps and record.steps[-1].success is None:
                raise RuntimeError('Nao e possivel concluir com passo incerto.')
            self._transition(record, TaskState.COMPLETED)
            record.result = str(result or "")
            record.finished_at = self._now()
            return self.snapshot(record.task_id)

    @_persistent_change
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

    @_persistent_change
    def request_cancel(self, task_id: str | None = None) -> TaskSnapshot:
        with self._lock:
            record = self._require(task_id)
            self._ensure_not_terminal(record, "solicitar cancelamento")
            record.cancel_requested = True
            return self.snapshot(record.task_id)

    @_persistent_change
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
                plan=record.plan,
                model_calls=record.model_calls,
                model_limit=record.model_limit,
                checkpoint_steps=record.checkpoint_steps,
                permission_limits=deepcopy(record.permission_limits),
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

    @_persistent_change
    def clear_current(self) -> None:
        with self._lock:
            current = self.current_snapshot()
            if current is not None and current.state in {TaskState.CREATED, TaskState.RUNNING, TaskState.WAITING}:
                raise RuntimeError('Nao e permitido desanexar tarefa em execucao.')
            self._current_task_id = None

    @_persistent_change
    def pause(self, task_id=None):
        record = self._require(task_id)
        if record.steps and record.steps[-1].success is None:
            raise RuntimeError('Nao e possivel pausar um passo incerto em andamento.')
        self._transition(record, TaskState.PAUSED)
        return self.snapshot(record.task_id)

    @_persistent_change
    def resume_checkpoint(self, task_id):
        record = self._require(task_id)
        if self._current_task_id and self._current_task_id != task_id:
            current = self._require(self._current_task_id)
            if current.state in {TaskState.CREATED, TaskState.RUNNING, TaskState.WAITING}:
                raise RuntimeError('Ja existe outra tarefa ativa; retomada recusada.')
        if record.state not in {TaskState.PAUSED, TaskState.INTERRUPTED}:
            raise RuntimeError('A tarefa nao esta pausada ou interrompida.')
        if record.cancel_requested:
            raise RuntimeError('Cancelamento pendente; retomada recusada.')
        if any(step.success is None for step in record.steps):
            raise RuntimeError('Passo incerto: verifique o efeito antes de qualquer retomada.')
        if any(step.success is False for step in record.steps):
            raise RuntimeError('Falha anterior exige nova verificacao antes da retomada.')
        self._transition(record, TaskState.RUNNING)
        if not record.started_at:
            record.started_at = self._now()
        self._current_task_id = record.task_id
        return self.snapshot(record.task_id)

    @_persistent_change
    def configure_model_budget(self, limit, task_id=None):
        record = self._require(task_id)
        self._ensure_not_terminal(record, 'configurar orcamento')
        if type(limit) is not int or limit < 1:
            raise ValueError('Limite de chamadas invalido.')
        if record.model_limit and limit > record.model_limit:
            raise RuntimeError('Nao e permitido aumentar o orcamento ao retomar.')
        if record.model_calls > limit:
            raise RuntimeError('Orcamento solicitado ja consumido.')
        record.model_limit = limit

    @_persistent_change
    def reserve_model_call(self, task_id=None):
        record = self._require(task_id)
        if record.state not in {TaskState.RUNNING, TaskState.WAITING}:
            raise RuntimeError('Tarefa nao esta em execucao.')
        if not record.model_limit or record.model_calls >= record.model_limit:
            raise RuntimeError('Limite acumulado de chamadas atingido.')
        record.model_calls += 1
        record.checkpoint_steps = -1

    @_persistent_change
    def save_execution_checkpoint(self, permission_limits, task_id=None):
        record = self._require(task_id)
        if record.state is not TaskState.RUNNING or any(s.success is not True for s in record.steps):
            raise RuntimeError('Checkpoint executavel exige passos sem incerteza ou falhas.')
        from core.permission_manager import PermissionManager
        PermissionManager().restore_limits(permission_limits)
        record.permission_limits = deepcopy(permission_limits)
        record.checkpoint_steps = len(record.steps)

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
