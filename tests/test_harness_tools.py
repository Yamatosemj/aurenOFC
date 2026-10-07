from __future__ import annotations

from types import SimpleNamespace

from core.browser_verification import verificar_resultado_navegador
from core.harness_tools import _executar_chamadas_rodada
from core.tool_result import ToolResult


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


        trace=trace,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,


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


        trace=trace,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,


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


        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=True,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,


        write_log=lambda *args, **kwargs: None,
    )

    assert results == []
    assert count == 0
    assert failed is True
    assert pending is False
    assert cancelled is True


def test_successful_browser_mutation_marks_verification_pending():
    manager = _TaskManager()
    state = {"pending": False}

    results, count, failed, vision_pending, cancelled = _executar_chamadas_rodada(
        [_item("clicar_elemento", "call-browser-1")],
        historico=[],
        task_manager=manager,
        task_id="task-browser-1",
        rodada=1,
        executar_ferramenta=lambda _: ToolResult.success(
            "Clique executado.",
            tool_name="clicar_elemento",
        ),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"clicar_elemento"},
        browser_verification_tool="obter_contexto_navegador",
    )

    assert results[0]["sucesso"] is True
    assert count == 1
    assert failed is False
    assert vision_pending is False
    assert cancelled is False
    assert state["pending"] is True


def test_successful_browser_context_clears_verification_pending():
    manager = _TaskManager()
    state = {"pending": True}

    results, count, failed, vision_pending, cancelled = _executar_chamadas_rodada(
        [_item("obter_contexto_navegador", "call-browser-2")],
        historico=[],
        task_manager=manager,
        task_id="task-browser-2",
        rodada=2,
        executar_ferramenta=lambda _: ToolResult.success(
            "Contexto atualizado.",
            tool_name="obter_contexto_navegador",
        ),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"clicar_elemento"},
        browser_verification_tool="obter_contexto_navegador",
    )

    assert results[0]["sucesso"] is True
    assert count == 1
    assert failed is False
    assert vision_pending is False
    assert cancelled is False
    assert state["pending"] is False


def test_browser_navigation_verification_clears_pending_only_when_target_matches():
    manager = _TaskManager()
    state = {"pending": False}
    chamadas = [
        _item("navegar_navegador", "call-browser-nav", '{"url":"youtube.com"}'),
        _item("obter_contexto_navegador", "call-browser-context", '{"foco":""}'),
    ]
    resultados = iter([
        ToolResult.success("Naveguei.", tool_name="navegar_navegador"),
        ToolResult.success(
            "contexto",
            tool_name="obter_contexto_navegador",
            data={
                "abas": (
                    "Abas abertas: 1\n"
                    "Aba ativa: 1\n"
                    "Aba 1: YouTube | https://www.youtube.com/ [ATIVA]"
                ),
                "pagina": "conteudo",
            },
        ),
    ])

    resultado = _executar_chamadas_rodada(
        chamadas,
        historico=[],
        task_manager=manager,
        task_id="task-browser-nav",
        rodada=1,
        executar_ferramenta=lambda _item: next(resultados),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"navegar_navegador"},
        browser_verification_tool="obter_contexto_navegador",
        browser_verifier=verificar_resultado_navegador,
    )

    assert state["pending"] is False


def test_browser_navigation_verification_keeps_pending_when_target_is_wrong():
    manager = _TaskManager()
    state = {"pending": False}
    chamadas = [
        _item("navegar_navegador", "call-browser-nav-2", '{"url":"youtube.com"}'),
        _item("obter_contexto_navegador", "call-browser-context-2", '{"foco":""}'),
    ]
    resultados = iter([
        ToolResult.success("Naveguei.", tool_name="navegar_navegador"),
        ToolResult.success(
            "contexto",
            tool_name="obter_contexto_navegador",
            data={
                "abas": (
                    "Abas abertas: 1\n"
                    "Aba ativa: 1\n"
                    "Aba 1: GitHub | https://github.com/ [ATIVA]"
                ),
                "pagina": "conteudo",
            },
        ),
    ])

    _executar_chamadas_rodada(
        chamadas,
        historico=[],
        task_manager=manager,
        task_id="task-browser-nav-2",
        rodada=1,
        executar_ferramenta=lambda _item: next(resultados),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"navegar_navegador"},
        browser_verification_tool="obter_contexto_navegador",
        browser_verifier=verificar_resultado_navegador,
    )

    assert state["pending"] is True



def test_browser_verification_state_survives_between_tool_rounds():
    manager = _TaskManager()
    state = {"pending": False}

    first = _executar_chamadas_rodada(
        [_item("rolar_pagina", "call-scroll-1", '{"direcao":"baixo"}')],
        historico=[],
        task_manager=manager,
        task_id="task-scroll-rounds",
        rodada=1,
        executar_ferramenta=lambda _item: ToolResult.success(
            "Pagina rolada para 'baixo'.",
            data={
                "direcao": "baixo",
                "scroll_y_antes": 0,
                "scroll_y_depois": 900,
                "scroll_height": 3000,
                "viewport_height": 900,
            },
            tool_name="rolar_pagina",
        ),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"rolar_pagina"},
        browser_verification_tool="obter_contexto_navegador",
        browser_verifier=verificar_resultado_navegador,
    )

    assert first[2] is False
    assert state["pending"] is True
    assert state["ferramenta"] == "rolar_pagina"
    assert state["argumentos"] == '{"direcao":"baixo"}'
    assert state["dados_acao"]["scroll_y_depois"] == 900

    second = _executar_chamadas_rodada(
        [_item("obter_contexto_navegador", "call-scroll-2", '{"foco":"comentarios"}')],
        historico=[],
        task_manager=manager,
        task_id="task-scroll-rounds",
        rodada=2,
        executar_ferramenta=lambda _item: ToolResult.success(
            "Contexto atualizado.",
            data={
                "abas": (
                    "Abas abertas: 1\n"
                    "Aba ativa: 1\n"
                    "Aba 1: Site | https://example.com [ATIVA]"
                ),
                "pagina": "comentarios",
                "scroll": {
                    "scroll_y": 900,
                    "scroll_height": 3000,
                    "viewport_height": 900,
                },
            },
            tool_name="obter_contexto_navegador",
        ),
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
        max_tool_result_chars=100,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *args, **kwargs: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"rolar_pagina"},
        browser_verification_tool="obter_contexto_navegador",
        browser_verifier=verificar_resultado_navegador,
    )

    assert second[2] is False
    assert state["pending"] is False
    assert "ferramenta" not in state
    assert "argumentos" not in state
    assert "dados_acao" not in state
