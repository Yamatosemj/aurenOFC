from __future__ import annotations

from core.harness_model import _executar_rodada_modelo


class _TaskManager:
    def __init__(self):
        self.events = []

    def wait_for_model(self, task_id):
        self.events.append(("wait", task_id))

    def resume(self, task_id):
        self.events.append(("resume", task_id))


def test_rodada_do_modelo_preserva_ordem_e_registro_da_requisicao():
    task_manager = _TaskManager()
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
    task_manager = _TaskManager()

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
    task_manager = _TaskManager()
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
