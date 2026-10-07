from __future__ import annotations

from core.harness_model import _log_resposta_modelo


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
