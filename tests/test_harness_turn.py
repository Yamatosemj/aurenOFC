from __future__ import annotations

from core.harness_turn import _registrar_turno


class _Context:
    persiste = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def record_turn(self, chat_id, papel, conteudo):
        if self.fail:
            raise RuntimeError("memory down")
        self.calls.append((chat_id, papel, conteudo))
        return {"ok": True}


class _Logger:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, event, **details) -> None:
        self.calls.append((event, details))


def test_turn_is_recorded_with_chat_id_and_original_text():
    context = _Context()
    log = _Logger()

    _registrar_turno(
        "user",
        "  texto com espacos  ",
        context=context,
        chat_id="chat-1",
        task_id="task-1",
        write_log=log,
    )

    assert context.calls == [("chat-1", "user", "  texto com espacos  ")]
    assert log.calls == []


def test_blank_turn_is_ignored_without_touching_context():
    context = _Context()
    log = _Logger()

    _registrar_turno(
        "assistant",
        "   \n\t  ",
        context=context,
        chat_id="chat-2",
        task_id="task-2",
        write_log=log,
    )

    assert context.calls == []
    assert log.calls == []


def test_non_persistent_context_is_ignored():
    context = _Context()
    context.persiste = False
    log = _Logger()

    _registrar_turno(
        "user",
        "texto",
        context=context,
        chat_id="chat-3",
        task_id="task-3",
        write_log=log,
    )

    assert context.calls == []
    assert log.calls == []


def test_record_failure_is_logged_without_escaping():
    context = _Context(fail=True)
    log = _Logger()

    _registrar_turno(
        "assistant",
        "texto",
        context=context,
        chat_id="chat-4",
        task_id="task-4",
        write_log=log,
    )

    assert log.calls == [
        (
            "MEMORY_ERROR",
            {
                "task_id": "task-4",
                "erro": "historico_assistant: memory down",
            },
        )
    ]


def test_empty_chat_id_is_preserved():
    context = _Context()
    log = _Logger()

    _registrar_turno(
        "user",
        "texto",
        context=context,
        chat_id="",
        task_id="task-5",
        write_log=log,
    )

    assert context.calls == [("", "user", "texto")]
    assert log.calls == []
