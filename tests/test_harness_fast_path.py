from __future__ import annotations

from core.harness_fast_path import _executar_fast_path


class _TaskManager:
    def __init__(self, *, cancelled: bool = False):
        self.cancelled = cancelled
        self.events = []
        self.failed = None
        self.completed = None
        self.cancelled_with = None

    def begin_step(self, *args, **kwargs):
        self.events.append(("begin_step", args, kwargs))

    def finish_step(self, **kwargs):
        self.events.append(("finish_step", kwargs))

    def should_cancel(self, task_id):
        self.events.append(("should_cancel", task_id))
        return self.cancelled

    def fail(self, error, *, task_id=None):
        self.failed = (error, task_id)
        self.events.append(("fail", error, task_id))

    def cancel(self, *, task_id=None, reason=""):
        self.cancelled_with = (task_id, reason)
        self.events.append(("cancel", task_id, reason))

    def complete(self, result, *, task_id=None):
        self.completed = (result, task_id)
        self.events.append(("complete", result, task_id))


class _Trace:
    def __init__(self):
        self.events = []

    def record_stage(self, *args, **kwargs):
        self.events.append((args, kwargs))


def _run(task_manager, comando, *, trace=None, logs=None, turns=None):
    logs = [] if logs is None else logs
    turns = [] if turns is None else turns
    return _executar_fast_path(
        "mensagem",
        comando_rapido=comando,
        task_manager=task_manager,
        task_id="task-1",
        trace=trace,
        max_tool_result_chars=100,
        texto_seguro=lambda value, limit: str(value)[:limit],
        registrar_turno=lambda papel, texto: turns.append((papel, texto)),
        write_log=lambda evento, **detalhes: logs.append((evento, detalhes)),
        resposta_wrapper=lambda text: ("wrapped", text),
    )


def test_fast_path_nao_tratado_retorna_none_e_nao_finaliza():
    manager = _TaskManager()

    result = _run(manager, lambda _m: (False, ""))

    assert result is None
    assert manager.failed is None
    assert manager.completed is None


def test_fast_path_bem_sucedido_completa_tarefa_e_preserva_resposta():
    manager = _TaskManager()
    logs = []
    turns = []

    result = _run(manager, lambda _m: (True, "ok"), logs=logs, turns=turns)

    assert result == (True, "ok")
    assert manager.completed == ("ok", "task-1")
    assert turns == [("assistant", "ok")]
    assert logs[-1] == ("TASK_END", {"task_id": "task-1", "status": "fast_path"})


def test_fast_path_falha_por_marcador_textual_nao_chega_ao_ciclo_normal():
    manager = _TaskManager()
    logs = []

    result = _run(
        manager,
        lambda _m: (True, "Nao consegui executar a acao"),
        logs=logs,
    )

    assert result == (True, ("wrapped", "Nao consegui executar a acao"))
    assert manager.failed == ("fast_path_failed", "task-1")
    assert logs[-1] == (
        "TASK_END",
        {
            "task_id": "task-1",
            "status": "failed",
            "motivo": "fast_path_failed",
        },
    )


def test_fast_path_respeita_cancelamento_antes_de_completar():
    manager = _TaskManager(cancelled=True)
    logs = []

    result = _run(manager, lambda _m: (True, "ok"), logs=logs)

    assert result == (True, ("wrapped", "Tarefa cancelada."))
    assert manager.cancelled_with == (
        "task-1",
        "cancelado antes da conclusao do fast path",
    )
    assert manager.completed is None
    assert logs[-1] == (
        "TASK_END",
        {
            "task_id": "task-1",
            "status": "cancelled",
            "motivo": "fast_path",
        },
    )


def test_fast_path_registra_etapa_de_trace_sem_bloquear_execucao():
    manager = _TaskManager()
    trace = _Trace()

    result = _run(manager, lambda _m: (False, ""), trace=trace)

    assert result is None
    assert len(trace.events) == 1
    args, kwargs = trace.events[0]
    assert args[0] == "fast_path"
    assert args[1] >= 0
    assert kwargs == {
        "category": "fast_path",
        "success": False,
    }


def test_fast_path_falha_de_trace_nao_interrompe_a_tarefa():
    manager = _TaskManager()

    class FailingTrace:
        def record_stage(self, *args, **kwargs):
            raise RuntimeError("trace failure")

    logs = []
    result = _run(
        manager,
        lambda _m: (True, "ok"),
        trace=FailingTrace(),
        logs=logs,
    )

    assert result == (True, "ok")
    assert any(
        evento == "TRACE_ERROR"
        and detalhes == {
            "task_id": "task-1",
            "etapa": "fast_path",
            "erro": "trace failure",
        }
        for evento, detalhes in logs
    )
