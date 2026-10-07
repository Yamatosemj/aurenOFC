from __future__ import annotations

from types import SimpleNamespace

from core.harness_tools import _executar_chamadas_rodada
from core.tool_result import ToolResult, from_legacy


class _TaskManager:
    def __init__(self, cancel_sequence=None):
        self.cancel_sequence = list(cancel_sequence or [])
        self.events = []

    def should_cancel(self, task_id):
        self.events.append(("should_cancel", task_id))
        if self.cancel_sequence:
            return self.cancel_sequence.pop(0)
        return False

    def begin_step(self, tool, arguments, *, task_id, step):
        self.events.append(("begin_step", tool, arguments, task_id, step))

    def finish_step(self, *, success, result, error, task_id):
        self.events.append(("finish_step", success, result, error, task_id))


class _Trace:
    def __init__(self):
        self.events = []

    def record_tool(self, name, latency_ms, *, success):
        self.events.append((name, latency_ms, success))


def _item(name, call_id, arguments="{}"):
    return SimpleNamespace(name=name, call_id=call_id, arguments=arguments)


def test_executes_calls_and_updates_history_and_results():
    manager = _TaskManager()
    trace = _Trace()
    logs = []
    history = []
    calls = []

    results, count, failed, pending, cancelled = _executar_chamadas_rodada(
        [_item("obter_status_windows", "call-1", '{"modo":"rapido"}')],
        historico=history,
        task_manager=manager,
        task_id="task-1",
        rodada=2,
        executar_ferramenta=lambda item: calls.append(item.name) or "ok",
        argumentos_da_chamada=lambda item: item.arguments,
        texto_seguro=lambda value, limit: value[:limit],
        trace=trace,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        from_legacy=from_legacy,
        tool_result_failure=ToolResult.failure,
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
    )

    assert calls == ["obter_status_windows"]
    assert count == 1
    assert failed is False
    assert pending is False
    assert cancelled is False
    assert history == [
        {
            "ferramenta": "obter_status_windows",
            "argumentos": '{"modo":"rapido"}',
            "resultado": "ok",
        }
    ]
    assert results[0]["call_id"] == "call-1"
    assert results[0]["sucesso"] is True
    assert results[0]["resultado"] == "ok"
    assert trace.events and trace.events[0][0] == "obter_status_windows"
    assert trace.events[0][2] is True
    assert logs[0][0] == ("TOOL_CALL",)
    assert logs[1][0] == ("TOOL_RESULT",)


def test_tool_exception_becomes_structured_failure_and_marks_step_failed():
    manager = _TaskManager()
    history = []
    logs = []
    trace = _Trace()

    results, count, failed, pending, cancelled = _executar_chamadas_rodada(
        [_item("ferramenta_teste", "call-2")],
        historico=history,
        task_manager=manager,
        task_id="task-2",
        rodada=1,
        executar_ferramenta=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
        argumentos_da_chamada=lambda item: item.arguments,
        texto_seguro=lambda value, limit: value[:limit],
        trace=trace,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        from_legacy=from_legacy,
        tool_result_failure=ToolResult.failure,
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
    )

    assert count == 1
    assert failed is True
    assert pending is False
    assert cancelled is False
    assert results[0]["sucesso"] is False
    assert "Falha inesperada no harness: boom" in results[0]["resultado"]
    finish = [event for event in manager.events if event[0] == "finish_step"]
    assert finish and finish[0][1] is False
    assert trace.events and trace.events[0][2] is False
    assert logs[1][0] == ("TOOL_RESULT",)


def test_successful_visual_mutation_invalidates_active_geometry():
    manager = _TaskManager()
    history = []
    state = {"geometry": object(), "cleared": 0}

    results, count, failed, pending, cancelled = _executar_chamadas_rodada(
        [_item("clicar_mouse_windows", "call-3")],
        historico=history,
        task_manager=manager,
        task_id="task-3",
        rodada=4,
        executar_ferramenta=lambda _: "cliquei",
        argumentos_da_chamada=lambda item: item.arguments,
        texto_seguro=lambda value, limit: value[:limit],
        trace=None,
        vision_state_mutating_tools={"clicar_mouse_windows"},
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: state["geometry"],
        clear_active_vision_geometry=lambda: (
            state.__setitem__("geometry", None),
            state.__setitem__("cleared", state["cleared"] + 1),
        ),
        from_legacy=from_legacy,
        tool_result_failure=ToolResult.failure,
        write_log=lambda *args, **kwargs: None,
    )

    assert results[0]["sucesso"] is True
    assert count == 1
    assert failed is False
    assert pending is True
    assert cancelled is False
    assert state["geometry"] is None
    assert state["cleared"] == 1


def test_cancellation_before_execution_preserves_previous_failure_state():
    manager = _TaskManager(cancel_sequence=[True])
    history = []

    results, count, failed, pending, cancelled = _executar_chamadas_rodada(
        [_item("ferramenta_teste", "call-4")],
        historico=history,
        task_manager=manager,
        task_id="task-4",
        rodada=5,
        executar_ferramenta=lambda _: "nao deveria executar",
        argumentos_da_chamada=lambda item: item.arguments,
        texto_seguro=lambda value, limit: value[:limit],
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=True,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        from_legacy=from_legacy,
        tool_result_failure=ToolResult.failure,
        write_log=lambda *args, **kwargs: None,
    )

    assert results == []
    assert count == 0
    assert failed is True
    assert pending is False
    assert cancelled is True
