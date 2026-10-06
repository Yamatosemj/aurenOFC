from __future__ import annotations

from threading import Event

from core.harness_strategy import _salvar_estrategia_em_background


class _Context:
    persiste = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def record_strategy(self, objetivo, passos, resultado, sucesso, *, chat_id=None):
        if self.fail:
            raise RuntimeError("memory down")
        self.calls.append(
            {
                "objetivo": objetivo,
                "passos": passos,
                "resultado": resultado,
                "sucesso": sucesso,
                "chat_id": chat_id,
            }
        )
        return {"ok": True}


class _Queue:
    def __init__(self, *, task_id: str = "background-1", fail: bool = False) -> None:
        self.task_id = task_id
        self.fail = fail
        self.calls = []

    def submit(self, goal, runner, *, priority):
        if self.fail:
            raise RuntimeError("queue down")
        self.calls.append(
            {
                "goal": goal,
                "runner": runner,
                "priority": priority,
            }
        )
        return self.task_id


class _Logger:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, event, **details) -> None:
        self.calls.append((event, details))


def test_strategy_is_queued_with_captured_chat_and_compacted_steps():
    context = _Context()
    queue = _Queue()
    log = _Logger()

    _salvar_estrategia_em_background(
        "objetivo de teste",
        [
            {"ferramenta": "f1", "resultado": "x" * 300},
            {"ferramenta": "f2"},
        ],
        "resultado final",
        True,
        context=context,
        background_queue=queue,
        task_id="task-1",
        chat_id="chat-1",
        write_log=log,
    )

    assert len(queue.calls) == 1
    call = queue.calls[0]
    assert call["goal"] == "salvar estrategia: objetivo de teste"
    assert call["priority"] == 100
    assert log.calls == [
        (
            "BACKGROUND_TASK_QUEUED",
            {
                "task_id": "task-1",
                "background_task_id": "background-1",
                "tipo": "salvar_estrategia",
            },
        )
    ]

    result = call["runner"](Event())
    assert result == {"ok": True}
    assert context.calls == [
        {
            "objetivo": "objetivo de teste",
            "passos": ["f1: " + "x" * 240, "f2: "],
            "resultado": "resultado final",
            "sucesso": True,
            "chat_id": "chat-1",
        }
    ]


def test_cancelled_background_runner_does_not_record_strategy():
    context = _Context()
    queue = _Queue()
    log = _Logger()
    cancel_event = Event()
    cancel_event.set()

    _salvar_estrategia_em_background(
        "objetivo",
        [{"ferramenta": "f1", "resultado": "ok"}],
        "resultado",
        context=context,
        background_queue=queue,
        task_id="task-2",
        chat_id="chat-2",
        write_log=log,
    )

    assert context.calls == []
    assert queue.calls[0]["runner"](cancel_event) == {
        "ok": False,
        "cancelado": True,
    }


def test_queue_failure_falls_back_to_synchronous_recording():
    context = _Context()
    queue = _Queue(fail=True)
    log = _Logger()

    _salvar_estrategia_em_background(
        "objetivo",
        [{"ferramenta": "f1", "resultado": "ok"}],
        "resultado",
        False,
        context=context,
        background_queue=queue,
        task_id="task-3",
        chat_id=None,
        write_log=log,
    )

    assert context.calls == [
        {
            "objetivo": "objetivo",
            "passos": ["f1: ok"],
            "resultado": "resultado",
            "sucesso": False,
            "chat_id": None,
        }
    ]
    assert log.calls == []


def test_failed_queue_and_failed_fallback_are_logged():
    context = _Context(fail=True)
    queue = _Queue(fail=True)
    log = _Logger()

    _salvar_estrategia_em_background(
        "objetivo",
        [{"ferramenta": "f1", "resultado": "ok"}],
        "resultado",
        context=context,
        background_queue=queue,
        task_id="task-4",
        chat_id="chat-4",
        write_log=log,
    )

    assert log.calls == [
        (
            "MEMORY_ERROR",
            {
                "task_id": "task-4",
                "erro": "estrategia: memory down",
                "fila_erro": "queue down",
            },
        )
    ]


def test_strategy_persistence_is_skipped_without_persistence_or_history():
    context = _Context()
    queue = _Queue()
    log = _Logger()

    context.persiste = False
    _salvar_estrategia_em_background(
        "objetivo",
        [{"ferramenta": "f1", "resultado": "ok"}],
        "resultado",
        context=context,
        background_queue=queue,
        task_id="task-5",
        chat_id="chat-5",
        write_log=log,
    )

    context.persiste = True
    _salvar_estrategia_em_background(
        "objetivo",
        [],
        "resultado",
        context=context,
        background_queue=queue,
        task_id="task-6",
        chat_id="chat-6",
        write_log=log,
    )

    assert context.calls == []
    assert queue.calls == []
    assert log.calls == []
