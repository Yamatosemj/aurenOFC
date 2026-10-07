from __future__ import annotations

from types import SimpleNamespace

from core.harness_session import _encerrar_sessao_chat, _garantir_sessao_chat


class _Session:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id


def test_existing_session_is_reused_and_rebound_to_current_context():
    session = _Session("chat-existing")
    created = []
    current = []

    result = _garantir_sessao_chat(
        session,
        criar_sessao=lambda: created.append(True),
        definir_sessao_atual=current.append,
    )

    assert result == (session, False, "chat-existing")
    assert created == []
    assert current == [session]


def test_missing_session_is_created_and_marked_as_started_here():
    created_session = _Session("chat-new")
    created = []
    current = []

    result = _garantir_sessao_chat(
        None,
        criar_sessao=lambda: created.append(created_session) or created_session,
        definir_sessao_atual=current.append,
    )

    assert result == (created_session, True, "chat-new")
    assert created == [created_session]
    assert current == [created_session]


def test_session_creator_is_called_only_when_session_is_missing():
    session = _Session("chat-existing")
    calls = []

    _garantir_sessao_chat(
        session,
        criar_sessao=lambda: calls.append("created") or _Session("wrong"),
        definir_sessao_atual=lambda _: None,
    )

    assert calls == []


def test_closing_missing_session_does_nothing():
    events = []

    result = _encerrar_sessao_chat(
        None,
        obter_sessao_atual=lambda: events.append("get-current") or None,
        limpar_sessao_atual=lambda: events.append("clear-current"),
        limpar_estado_harness=lambda: events.append("clear-harness"),
        limpar_redaction=lambda: events.append("clear-redaction"),
        write_log=lambda *args, **_: events.append("write-log"),
    )

    assert result is False
    assert events == []


def test_closing_session_clears_matching_context_and_all_state():
    session = _Session("chat-close")
    current = [session]
    events = []

    result = _encerrar_sessao_chat(
        session,
        status="closed-by-test",
        obter_sessao_atual=lambda: current[0],
        limpar_sessao_atual=lambda: (events.append("clear-current"), current.__setitem__(0, None)),
        limpar_estado_harness=lambda: events.append("clear-harness"),
        limpar_redaction=lambda: events.append("clear-redaction"),
        write_log=lambda *args, **kwargs: events.append(("write-log", args, kwargs)),
    )

    assert result is True
    assert current == [None]
    assert events == [
        ("write-log", ("CHAT_END",), {"chat_id": "chat-close", "status": "closed-by-test"}),
        "clear-current",
        "clear-harness",
        "clear-redaction",
    ]


def test_closing_session_does_not_clear_a_different_current_context():
    session = _Session("chat-close")
    other = _Session("chat-other")
    current = [other]
    events = []

    result = _encerrar_sessao_chat(
        session,
        obter_sessao_atual=lambda: current[0],
        limpar_sessao_atual=lambda: events.append("clear-current"),
        limpar_estado_harness=lambda: events.append("clear-harness"),
        limpar_redaction=lambda: events.append("clear-redaction"),
        write_log=lambda *args, **_: events.append("write-log"),
    )

    assert result is True
    assert current == [other]
    assert events == ["write-log", "clear-harness", "clear-redaction"]


def test_closing_session_runs_cleanup_when_log_writer_raises():
    session = _Session("chat-error")
    events = []

    def write_log(*args, **_):
        events.append("write-log")
        raise RuntimeError("log failure")

    try:
        _encerrar_sessao_chat(
            session,
            obter_sessao_atual=lambda: session,
            limpar_sessao_atual=lambda: events.append("clear-current"),
            limpar_estado_harness=lambda: events.append("clear-harness"),
            limpar_redaction=lambda: events.append("clear-redaction"),
            write_log=write_log,
        )
    except RuntimeError as exc:
        assert str(exc) == "log failure"
    else:
        raise AssertionError("a excecao do logger deveria ser propagada")

    assert events == [
        "write-log",
        "clear-current",
        "clear-harness",
        "clear-redaction",
    ]


def test_browser_mutation_is_blocked_while_verification_is_pending():
    from core.harness_tools import _executar_chamadas_rodada
    from core.tool_result import ToolResult

    class TaskManager:
        def should_cancel(self, _task_id): return False
        def begin_step(self, *_args, **_kwargs): pass
        def finish_step(self, *_args, **_kwargs): pass

    called = []
    state = {
        "pending": True,
        "ferramenta": "clicar_elemento",
        "argumentos": '{"alvo":"Salvar","indice":1}',
        "dados_acao": {},
    }
    resultados, _, _, _, _ = _executar_chamadas_rodada(
        chamadas=[
            SimpleNamespace(
                name="clicar_elemento",
                arguments='{"alvo":"Outro","indice":1}',
            )
        ],
        task_manager=TaskManager(),
        executar_ferramenta=lambda item: called.append(item) or ToolResult.success("executado"),
        task_id="chat",
        rodada=2,
        historico=[],
        max_tool_result_chars=4000,
        get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None,
        write_log=lambda *_a, **_k: None,
        browser_verification_state=state,
        browser_state_mutating_tools={"clicar_elemento"},
        browser_verifier=lambda *_a: True,
        trace=None,
        vision_state_mutating_tools=set(),
        vision_reobserve_pending=False,
        falha_nao_recuperada=False,
    )
    assert resultados[0]["sucesso"] is False
    assert resultados[0]["dados"].get("codigo_erro") == "browser_verification_required"
    assert called == []
