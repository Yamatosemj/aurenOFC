from __future__ import annotations

from core.harness_model import _executar_rodada_modelo, _log_resposta_modelo


class _Trace:
    def __init__(self, events):
        self.events = events

    def record_model(self, rodada, latencia_ms, uso):
        self.events.append(("record_model", rodada, latencia_ms, uso))


class _Resposta:
    output = ["item-1", "item-2"]
    output_text = "resposta final"


def test_logs_model_response_and_records_trace():
    events = []
    resposta = _Resposta()

    _log_resposta_modelo(
        3,
        resposta,
        123.4567,
        {"modelo": "gpt-test"},
        trace=_Trace(events),
        task_id="task-3",
        uso_resposta=lambda value: {"tokens": 42} if value is resposta else {},
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
        rodada_extra="extra",
    )

    assert events == [
        ("record_model", 3, 123.4567, {"tokens": 42}),
        (
            "write_log",
            ("MODEL_ROUND_RESPONSE",),
            {
                "task_id": "task-3",
                "rodada": 3,
                "output_items": 2,
                "output_text": "resposta final",
                "uso": {"tokens": 42},
                "latencia_ms": 123.457,
                "router": {"modelo": "gpt-test"},
                "rodada_extra": "extra",
            },
        ),
    ]


def test_trace_failure_is_logged_and_model_response_still_reaches_log():
    events = []
    resposta = _Resposta()

    class _FailingTrace:
        def record_model(self, rodada, latencia_ms, uso):
            events.append(("record_model", rodada, latencia_ms, uso))
            raise RuntimeError("trace failure")

    _log_resposta_modelo(
        4,
        resposta,
        9.5,
        {},
        trace=_FailingTrace(),
        task_id="task-4",
        uso_resposta=lambda _: 7,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
    )

    assert events == [
        ("record_model", 4, 9.5, 7),
        (
            "write_log",
            ("TRACE_ERROR",),
            {"task_id": "task-4", "etapa": "model", "erro": "trace failure"},
        ),
        (
            "write_log",
            ("MODEL_ROUND_RESPONSE",),
            {
                "task_id": "task-4",
                "rodada": 4,
                "output_items": 2,
                "output_text": "resposta final",
                "uso": 7,
                "latencia_ms": 9.5,
                "router": {},
            },
        ),
    ]


def test_missing_trace_skips_trace_recording():
    events = []

    _log_resposta_modelo(
        5,
        _Resposta(),
        1.0,
        {"rota": "local"},
        trace=None,
        task_id="task-5",
        uso_resposta=lambda _: 0,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
    )

    assert events == [
        (
            "write_log",
            ("MODEL_ROUND_RESPONSE",),
            {
                "task_id": "task-5",
                "rodada": 5,
                "output_items": 2,
                "output_text": "resposta final",
                "uso": 0,
                "latencia_ms": 1.0,
                "router": {"rota": "local"},
            },
        ),
    ]



class _RoundTaskManager:
    def __init__(self):
        self.events = []

    def wait_for_model(self, task_id):
        self.events.append(("wait", task_id))

    def resume(self, task_id):
        self.events.append(("resume", task_id))


def test_rodada_do_modelo_preserva_ordem_e_registro_da_requisicao():
    task_manager = _RoundTaskManager()
    events = []

    def pedir_modelo(entrada, tool_choice):
        events.append(("call", entrada, tool_choice))
        return ("resposta", 12.5, {"rota": "default"})

    def log_resposta(*args):
        events.append(("response", args))

    def write_log(evento, **detalhes):
        events.append(("log", evento, detalhes))

    result = _executar_rodada_modelo(
        "estado",
        rodada=1,
        task_id="task-1",
        task_manager=task_manager,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        write_log=write_log,
        input_items=1,
        estado_chars=5,
        tool_choice="required",
        log_tool_choice="required",
    )

    assert result == ("resposta", 12.5, {"rota": "default"})
    assert task_manager.events == [("wait", "task-1"), ("resume", "task-1")]
    assert events[0] == (
        "log",
        "MODEL_ROUND_REQUEST",
        {
            "task_id": "task-1",
            "rodada": 1,
            "input_items": 1,
            "estado_chars": 5,
            "tool_choice": "required",
        },
    )
    assert events[1] == ("call", "estado", "required")
    assert events[2][0] == "response"


def test_rodada_do_modelo_sem_resposta_nao_retoma_task_manager():
    task_manager = _RoundTaskManager()

    result = _executar_rodada_modelo(
        [],
        rodada=2,
        task_id="task-2",
        task_manager=task_manager,
        pedir_modelo=lambda *_: None,
        log_resposta_modelo=lambda *_: None,
        write_log=lambda *_args, **_kwargs: None,
        input_items=0,
        estado_chars=0,
    )

    assert result is None
    assert task_manager.events == [("wait", "task-2")]


def test_rodada_seguinte_nao_adiciona_tool_choice_ao_log():
    task_manager = _RoundTaskManager()
    logs = []

    result = _executar_rodada_modelo(
        [{"type": "function_call_output"}],
        rodada=2,
        task_id="task-3",
        task_manager=task_manager,
        pedir_modelo=lambda entrada, choice: ("ok", 1.0, {}),
        log_resposta_modelo=lambda *_: None,
        write_log=lambda evento, **detalhes: logs.append((evento, detalhes)),
        input_items=1,
        estado_chars=10,
    )

    assert result == ("ok", 1.0, {})
    assert logs == [
        (
            "MODEL_ROUND_REQUEST",
            {
                "task_id": "task-3",
                "rodada": 2,
                "input_items": 1,
                "estado_chars": 10,
            },
        )
    ]
