"""Ponte entre interface desktop e o Harness V47.

Nenhuma ferramenta executa fora do Router/Dispatcher. Nenhuma chamada Tk ocorre
nas threads de trabalho; resultados e confirmacoes trafegam por Queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue, Empty
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
from core.execution_scope import current_session_guard
from core.execution_progress import observer


@dataclass
class UiEvent:
    kind: str
    text: str = ""
    payload: Any = None
    generation: int | None = None


@dataclass
class ConfirmationChoice:
    action: str
    reason: str
    tool_name: str
    decided: Event = field(default_factory=Event)
    approved: bool = False
    _answer_lock: Lock = field(default_factory=Lock, repr=False)

    def answer(self, approve: bool) -> None:
        # A interface e o cancelamento podem responder em threads diferentes.
        with self._answer_lock:
            if not self.decided.is_set():
                self.approved = bool(approve)
                self.decided.set()


class GuiConfirmationChannel:
    """Solicita aprovacao na UI; timeout/fechamento sempre negam a acao."""

    def __init__(
        self,
        events: Queue[UiEvent],
        register_pending: Callable[[ConfirmationChoice | None], None],
        *,
        timeout: float = 45.0,
        generation: int | None = None,
        is_current: Callable[[], bool] | None = None,
    ) -> None:
        self.events = events
        self.register_pending = register_pending
        self.timeout = timeout
        self.generation = generation
        self.is_current = is_current

    def confirmar(self, request: Any) -> bool:
        choice = ConfirmationChoice(
            action=str(request.action),
            reason=str(request.reason),
            tool_name=str(request.tool_name),
        )
        self.register_pending(choice)
        try:
            # Cancelamento/Desligado pode ocorrer antes da publicacao do modal.
            # Nao deixar uma confirmacao antiga esperando 45 s ou ser aprovada.
            if self.is_current is not None and not self.is_current():
                choice.answer(False)
                return False
            if choice.decided.is_set():
                return False
            self.events.put(UiEvent("confirm", payload=choice, generation=self.generation))
            if not choice.decided.wait(self.timeout):
                choice.answer(False)
                self.events.put(UiEvent("notice", "Confirmacao expirada. Acao negada.", generation=self.generation))
            return bool(choice.approved)
        finally:
            self.register_pending(None)
            self.events.put(UiEvent("confirm_done", payload=choice, generation=self.generation))


class AurenUiWorker:
    """Serializa tarefas em uma thread e mantém uma unica sessao do Harness."""

    def __init__(self, harness_factory: Callable[..., Any] | None = None, *, task_db_path=None) -> None:
        self.events: Queue[UiEvent] = Queue()
        self._requests: Queue[tuple[str, Any, int]] = Queue()
        self._harness_factory = harness_factory
        self._harness: Any = None
        self._scheduler = None
        self._task_db_path = task_db_path if task_db_path is not None else Path(__file__).resolve().parents[1]/'data'/'tasks'/'auren_tasks.sqlite3'
        self._pending: ConfirmationChoice | None = None
        self._lock = Lock()
        self._enabled = False
        self._generation = 0
        self._closing = Event()
        self._thread = Thread(target=self._run, name="auren-ui-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def _generation_is_active(self, generation: int) -> bool:
        with self._lock:
            return self._enabled and generation == self._generation and not self._closing.is_set()

    def activate(self) -> None:
        with self._lock:
            if not self._closing.is_set():
                if not self._enabled:
                    # Reativar invalida o "off" ainda aguardando no worker.
                    self._generation += 1
                self._enabled = True

    def submit(self, text: str) -> bool:
        text = str(text or "").strip()
        with self._lock:
            if not text or self._closing.is_set() or not self._enabled:
                return False
            generation = self._generation
        self._requests.put(("message", text, generation))
        return True

    def _set_pending(self, choice: ConfirmationChoice | None) -> None:
        with self._lock:
            self._pending = choice

    def deny_pending(self) -> None:
        with self._lock:
            choice = self._pending
        if choice is not None:
            choice.answer(False)

    def cancel_current(self) -> None:
        self.deny_pending()
        with self._lock:
            harness = self._harness
        if harness is not None:
            try:
                snapshot = harness.current_task()
                if getattr(getattr(snapshot, 'state', None), 'value', '') in {'paused', 'interrupted'}:
                    return
                harness.cancel_current_task()
            except Exception:
                pass

    def go_off(self) -> None:
        if self._closing.is_set():
            return
        with self._lock:
            self._enabled = False
            self._generation += 1
            generation = self._generation
        self.cancel_current()
        self._requests.put(("off", "", generation))

    def close(self) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        with self._lock:
            self._enabled = False
            self._generation += 1
            generation = self._generation
        self.cancel_current()
        self._requests.put(("quit", "", generation))

    def _make_harness(self, generation: int) -> Any:
        channel = GuiConfirmationChannel(
            self.events, self._set_pending,
            generation=generation,
            is_current=lambda: self._generation_is_active(generation),
        )
        if self._harness_factory is not None:
            return self._harness_factory(confirmation_channel=channel)
        # Import tardio: abrir a janela nao conecta a API nem inicia a voz.
        import auren
        if self._task_db_path is False:
            return auren.criar_harness(confirmation_channel=channel)
        return auren.criar_harness(confirmation_channel=channel, task_db_path=self._task_db_path)

    def _dispose_harness(self) -> None:
        with self._lock:
            harness, self._harness = self._harness, None
        if harness is None:
            return
        self._scheduler = None
        shutdown = getattr(harness, 'shutdown', None)
        if callable(shutdown):
            try:
                shutdown(timeout=1.0)
            except Exception:
                self.events.put(UiEvent('notice', 'Nao foi possivel confirmar o encerramento completo da sessao.'))
            return
        # Mesma finalizacao de executar() no Harness, sem duplicar executores.
        try:
            bg = getattr(harness, "_background_queue", None)
            if bg is not None:
                bg.shutdown(cancel_pending=False)
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao encerrar tarefas: {exc}"))
        try:
            harness.fechar()
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao fechar navegador: {exc}"))
        try:
            harness._encerrar_sessao_chat("closed")
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao fechar sessao: {exc}"))

    def _run(self) -> None:
        try:
            while True:
                try:
                    operation, text, generation = self._requests.get(timeout=1.0)
                except Empty:
                    self._poll_routines()
                    continue
                if operation == "quit" or self._closing.is_set():
                    break
                if operation == "off":
                    self._dispose_harness()
                    self.events.put(UiEvent("off", generation=generation))
                    continue
                if operation not in {"message", "task", "routine"}:
                    continue
                with self._lock:
                    valid = self._enabled and generation == self._generation
                if not valid:
                    continue

                self.events.put(UiEvent("busy", "Pedido recebido. Preparando…", generation=generation))
                session_token = current_session_guard.set(lambda: self._generation_is_active(generation))
                progress_token = observer.set(lambda label: self.events.put(
                    UiEvent("progress", label, generation=generation))
                    if self._generation_is_active(generation) else None)
                try:
                    with self._lock:
                        harness = self._harness
                    if harness is None:
                        harness = self._make_harness(generation)
                        with self._lock:
                            self._harness = harness
                    with self._lock:
                        still_valid = self._enabled and generation == self._generation
                    if not still_valid or self._closing.is_set():
                        continue
                    self._ensure_task_services(harness)
                    if operation == 'task':
                        if text['action'] == 'select':
                            with self._lock:
                                harness.selecionar_chat(text['chat_id'])
                        if text['action'] in {'load', 'select'}:
                            self.events.put(UiEvent('tasks', payload=self.task_dashboard(), generation=generation))
                            continue
                        with self._lock:
                            harness.selecionar_chat(text['chat_id'])
                        quick, response = harness.retomar_tarefa(text['task_id'], chat_id=text['chat_id'])
                    elif operation == 'routine':
                        self._routine_control(harness, text, generation)
                        self.events.put(UiEvent('tasks', payload=self.task_dashboard(), generation=generation))
                        continue
                    else:
                        quick, response = harness.processar_mensagem(text)
                    answer = response if quick else getattr(response, "output_text", str(response))
                    answer = str(answer or "").strip() or "(Sem resposta textual.)"
                    # Desligar/reativar invalida resultados da geracao anterior.
                    with self._lock:
                        still_current = (
                            self._enabled
                            and generation == self._generation
                            and not self._closing.is_set()
                        )
                    if not still_current:
                        continue
                    snapshot = harness.current_task()
                    status = getattr(getattr(snapshot, "state", None), "value", "")
                    if status == "failed":
                        self.events.put(UiEvent("error", answer, generation=generation))
                    else:
                        self.events.put(UiEvent("reply", answer, generation=generation))
                except Exception as exc:
                    with self._lock:
                        still_current = (
                            self._enabled
                            and generation == self._generation
                            and not self._closing.is_set()
                        )
                    if still_current:
                        self.events.put(UiEvent("error", f"Erro ao processar: {exc}", generation=generation))
                finally:
                    observer.reset(progress_token)
                    current_session_guard.reset(session_token)
                    self.events.put(UiEvent("idle", generation=generation))
        finally:
            self.deny_pending()
            self._dispose_harness()
            self.events.put(UiEvent("closed"))

    def _ensure_task_services(self, harness):
        manager = getattr(harness, 'task_manager', None)
        if getattr(manager, 'persistent', False):
            harness._garantir_sessao_chat()
            if self._scheduler is None:
                from core.routines import RoutineScheduler
                self._scheduler = RoutineScheduler(manager)

    def task_dashboard(self):
        with self._lock:
            harness, generation = self._harness, self._generation
        empty = {'generation': generation, 'chat_id': '', 'chats': [], 'tasks': [], 'routines': []}
        manager = getattr(harness, 'task_manager', None)
        if not getattr(manager, 'persistent', False) or manager.closed:
            return empty
        try:
            chat_id = getattr(getattr(harness, '_session', None), 'chat_id', '')
            values = []
            for task in manager.list_snapshots(chat_id, limit=50):
                values.append({'task_id': task.task_id, 'objective': task.objective, 'state': task.state.value,
                    'steps_done': sum(step.success is True for step in task.steps),
                    'steps_total': len(task.steps), 'planned_steps': len(task.plan.steps) if task.plan else 0,
                    'model_calls': task.model_calls, 'model_limit': task.model_limit,
                    'current_tool': task.current_tool or '', 'cancel_requested': task.cancel_requested,
                    'can_resume': task.state.value in {'paused', 'interrupted'} and not task.cancel_requested
                        and task.checkpoint_steps == len(task.steps) and task.permission_limits is not None
                        and task.model_calls < task.model_limit,
                    'steps': [{'tool': s.tool, 'success': s.success, 'result': s.result[:300]} for s in task.steps[-20:]]})
            return {'generation': generation, 'chat_id': chat_id,
                'chats': sorted(set(manager.list_chat_ids()) | {chat_id}), 'tasks': values,
                'routines': self._scheduler.list(chat_id=chat_id) if self._scheduler else []}
        except RuntimeError:
            return empty

    def pending_notifications(self, *, chat_id=None, generation=None):
        with self._lock:
            if (not self._enabled or self._closing.is_set() or self._scheduler is None
                    or self._harness is None or self._scheduler.manager.closed
                    or (generation is not None and generation != self._generation)
                    or (chat_id is not None and chat_id != self._harness._session.chat_id)):
                return []
            return self._scheduler.pending_notifications(chat_id=self._harness._session.chat_id)

    def notification_action(self, action, *, notification_id, revision, chat_id, generation):
        with self._lock:
            if (action not in {'ack', 'snooze'} or type(generation) is not int
                    or generation != self._generation or not self._enabled or self._closing.is_set()
                    or self._harness is None or self._scheduler is None
                    or self._harness._session.chat_id != chat_id):
                return False
            method = (self._scheduler.acknowledge_notification if action == 'ack'
                      else self._scheduler.snooze_notification)
            return method(notification_id, revision, chat_id=chat_id)

    def task_action(self, action, *, generation, task_id='', chat_id=''):
        if action not in {'load', 'select', 'resume', 'pause', 'cancel'} or type(generation) is not int:
            return False
        with self._lock:
            if not self._enabled or self._closing.is_set() or generation != self._generation:
                return False
            harness = self._harness
        if action in {'pause', 'cancel'}:
            if harness is None:
                return False
            task = harness.task_manager.get_snapshot(task_id)
            if task.chat_id != chat_id:
                return False
            current = harness.current_task()
            if action == 'pause':
                return current is not None and current.task_id == task_id and harness.pause_current_task()
            self.deny_pending()
            if task.state.value in {'paused', 'interrupted'}:
                harness.task_manager.cancel(task_id=task_id)
                return True
            return current is not None and current.task_id == task_id and harness.cancel_current_task()
        self._requests.put(('task', {'action': action, 'task_id': task_id, 'chat_id': chat_id}, generation))
        return True

    def routine_action(self, action, *, generation, routine_id='', spec=None):
        if action not in {'register', 'authorize', 'revoke'} or type(generation) is not int:
            return False
        if not self._generation_is_active(generation):
            return False
        if action == 'revoke':
            if self._scheduler is None or self._harness is None:
                return False
            chat = self._harness._session.chat_id
            self._scheduler.revoke(routine_id, chat_id=chat)
            self.deny_pending()
            return True
        self._requests.put(('routine', {'action': action, 'routine_id': routine_id, 'spec': spec}, generation))
        return True

    def _routine_control(self, harness, data, generation):
        if self._scheduler is None:
            raise RuntimeError('Agenda persistente indisponivel.')
        chat = harness._session.chat_id
        if data['action'] == 'authorize':
            with self._lock:
                if not self._enabled or self._closing.is_set() or generation != self._generation:
                    raise RuntimeError('Sessao invalidada antes da autorizacao.')
                self._scheduler.authorize(data['routine_id'], chat_id=chat)
            return
        spec = data['spec']
        fields = {'kind', 'objective', 'due_at', 'expires_at', 'interval_seconds', 'max_runs'}
        if not isinstance(spec, dict) or set(spec) != fields:
            raise ValueError('Cadastro de rotina invalido.')
        options = {'read_volume': ('Qual o volume atual?', 'obter_audio_windows'),
                   'read_status': ('Qual o status atual do sistema?', 'obter_status_windows')}
        if spec['kind'] == 'reminder':
            objective, mode, calls, budget = spec['objective'], 'suggest', [], 0
        elif spec['kind'] in options:
            objective, name = options[spec['kind']]
            mode, calls, budget = 'execute', [{'name': name, 'arguments': {}}], 1
        else:
            raise ValueError('Tipo de rotina nao permitido nesta interface.')
        self._scheduler.register(chat_id=chat, objective=objective, due_at=spec['due_at'],
            expires_at=spec['expires_at'], interval_seconds=spec['interval_seconds'],
            max_runs=spec['max_runs'], mode=mode, allowed_calls=calls, model_budget=budget)

    def _poll_routines(self):
        with self._lock:
            harness, generation = self._harness, self._generation
            valid = self._enabled and not self._closing.is_set()
        if not valid or harness is None or self._scheduler is None:
            return
        started = False
        try:
            current = harness.current_task()
            if current is not None and current.state.value not in {'completed', 'failed', 'cancelled'}:
                return
            chat = harness._session.chat_id
            import time
            if not any(r['status'] == 'enabled' and r['next_due'] <= time.time() for r in self._scheduler.list(chat_id=chat)):
                return
            self.events.put(UiEvent('busy', generation=generation))
            started = True
            token = current_session_guard.set(lambda: self._generation_is_active(generation))
            try:
                for event in self._scheduler.tick(harness, chat_id=chat):
                    if self._generation_is_active(generation):
                        self.events.put(UiEvent('notice', 'Rotina: ' + event['text'] + ' — ' + event['kind'], generation=generation))
            finally:
                current_session_guard.reset(token)
        except Exception:
            self.events.put(UiEvent('notice', 'A rotina encontrou um erro e nao foi confirmada. Confira suas tarefas.', generation=generation))
        finally:
            # Consultar a agenda sem executar nada nao e atividade da sessao.
            if started:
                self.events.put(UiEvent('idle', generation=generation))
