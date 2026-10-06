"""Priority task queue para trabalho pos-tarefa do Auren."""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)
TaskCallable = Callable[[threading.Event], object]

@dataclass
class AgentQueuedTask:
    task_id: str
    goal: str
    runner: TaskCallable
    priority: int = 50
    created_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)

@dataclass
class AgentTaskResult:
    task_id: str
    goal: str
    status: str
    result: object = None
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

class AgentTaskQueue:
    """Fila com lifecycle explicito, sem substituicao silenciosa de tarefas."""
    def __init__(self, max_workers: int = 1, *, max_results: int = 200):
        self.max_workers = max(1, int(max_workers or 1))
        self.max_results = max(1, int(max_results or 1))
        self._queue: queue.PriorityQueue[tuple[int, int, AgentQueuedTask | None]] = queue.PriorityQueue()
        self._counter = itertools.count()
        self._pending: dict[str, AgentQueuedTask] = {}
        self._running: dict[str, AgentQueuedTask] = {}
        self._results: dict[str, AgentTaskResult] = {}
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self._shutdown_state = "running"
        self._workers = [
            threading.Thread(target=self._worker_loop, name=f"auren-ari-agent-task-queue-{idx}", daemon=True)
            for idx in range(self.max_workers)
        ]
        for worker in self._workers:
            worker.start()

    @property
    def shutdown_state(self) -> str:
        with self._lock:
            return self._shutdown_state

    @property
    def alive_workers(self) -> int:
        return sum(worker.is_alive() for worker in self._workers)

    def submit(self, goal: str, runner: TaskCallable, *, priority: int = 50, task_id: Optional[str] = None) -> str:
        if not callable(runner):
            raise TypeError("runner must be callable")
        task = AgentQueuedTask(task_id=task_id or uuid.uuid4().hex, goal=str(goal or ""), runner=runner, priority=int(priority))
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError("Task queue has been shut down")
            if task.task_id in self._pending or task.task_id in self._running or task.task_id in self._results:
                raise ValueError(f"task_id ja existe: {task.task_id}")
            self._pending[task.task_id] = task
            self._queue.put((task.priority, next(self._counter), task))
        return task.task_id

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._pending.get(task_id) or self._running.get(task_id)
            if task is None:
                return False
            task.cancel_event.set()
            return True

    def cancel_current(self, task_id: Optional[str] = None) -> int:
        with self._lock:
            running = list(self._running.values())
            if task_id is not None:
                running = [task for task in running if task.task_id == task_id]
            for task in running:
                task.cancel_event.set()
            return len(running)

    def status(self, task_id: str) -> str:
        with self._lock:
            if task_id in self._pending:
                return "pending"
            if task_id in self._running:
                return "running"
            result = self._results.get(task_id)
            return result.status if result else "unknown"

    def result(self, task_id: str) -> Optional[AgentTaskResult]:
        with self._lock:
            return self._results.get(task_id)

    def shutdown(self, *, cancel_pending: bool = True, timeout: float = 1.0) -> str:
        timeout = max(0.0, float(timeout))
        with self._lock:
            if self._shutdown_state == "stopped":
                return "stopped"
            self._shutdown.set()
            self._shutdown_state = "stopping" if self._shutdown_state == "running" else self._shutdown_state
            now = time.time()
            if cancel_pending:
                for task_id, task in list(self._pending.items()):
                    task.cancel_event.set()
                    self._pending.pop(task_id, None)
                    self._store_result_locked(AgentTaskResult(task_id=task.task_id, goal=task.goal, status="cancelled", finished_at=now))
                for task in self._running.values():
                    task.cancel_event.set()

        for _ in self._workers:
            self._queue.put((10**9, next(self._counter), None))

        deadline = time.monotonic() + timeout
        for worker in self._workers:
            worker.join(max(0.0, deadline - time.monotonic()))

        with self._lock:
            if any(worker.is_alive() for worker in self._workers):
                self._shutdown_state = "timed_out"
                return "timed_out"
            self._shutdown_state = "stopped"
            return "stopped"

    def _worker_loop(self) -> None:
        while True:
            try:
                _, _, task = self._queue.get(timeout=0.1)
            except queue.Empty:
                with self._lock:
                    if self._shutdown.is_set() and not self._pending and not self._running:
                        return
                continue
            try:
                if task is None:
                    return
                self._run_task(task)
            finally:
                self._queue.task_done()

    def _run_task(self, task: AgentQueuedTask) -> None:
        with self._lock:
            if self._pending.pop(task.task_id, None) is None:
                return
            if task.cancel_event.is_set():
                self._store_result_locked(AgentTaskResult(task_id=task.task_id, goal=task.goal, status="cancelled", finished_at=time.time()))
                return
            self._running[task.task_id] = task
        started_at = time.time()
        try:
            result = task.runner(task.cancel_event)
            status = "cancelled" if task.cancel_event.is_set() else "completed"
            task_result = AgentTaskResult(task_id=task.task_id, goal=task.goal, status=status, result=result, started_at=started_at, finished_at=time.time())
        except Exception as exc:
            logger.exception("[AgentTaskQueue] trabalho pós-tarefa falhou: %s", task.goal[:80])
            task_result = AgentTaskResult(task_id=task.task_id, goal=task.goal, status="failed", error=str(exc), started_at=started_at, finished_at=time.time())
        with self._lock:
            self._running.pop(task.task_id, None)
            self._store_result_locked(task_result)

    def _store_result_locked(self, task_result: AgentTaskResult) -> None:
        self._results[task_result.task_id] = task_result
        while len(self._results) > self.max_results:
            self._results.pop(next(iter(self._results)))
