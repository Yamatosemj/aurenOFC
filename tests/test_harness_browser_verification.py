from __future__ import annotations

from core.harness_guards import _tratar_rodada_sem_ferramentas
from tests.test_harness_guards import _TaskManager, _base_callbacks, _resposta


def test_browser_guard_retries_and_updates_counter():
    events = []
    manager = _TaskManager()
    montar_estado, pedir_modelo, log_resposta = _base_callbacks(
        events,
        [_resposta("verificado")],
    )

    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="clique no botao comprar",
        historico=[{"ferramenta": "clicar_elemento", "argumentos": "{}", "resultado": "Clique executado."}],
        rodada=2,
        exigir_ferramenta=True,
        ferramentas_executadas=1,
        resposta=_resposta("concluido"),
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-browser-guard-1",
        task_manager=manager,
        montar_estado=montar_estado,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
        browser_verification_pending=True,
        browser_verification_attempts=0,
    )

    assert resultado.acao == "continuar"
    assert resultado.browser_verification_attempts == 1
    assert resultado.resposta.output_text == "verificado"
    assert manager.events == [("wait", "task-browser-guard-1"), ("resume", "task-browser-guard-1")]
    assert any(
        item[0] == "write_log" and item[1][0] == "TASK_BROWSER_GUARD"
        for item in events
    )


def test_browser_guard_exhaustion_returns_failure():
    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="clique no botao comprar",
        historico=[],
        rodada=4,
        exigir_ferramenta=False,
        ferramentas_executadas=1,
        resposta=_resposta("aguardando"),
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-browser-guard-2",
        task_manager=_TaskManager(),
        montar_estado=lambda *args: "unused",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: None,
        browser_verification_pending=True,
        browser_verification_attempts=2,
    )

    assert resultado.acao == "falhar"
    assert resultado.failure_code == "browser_verification_missing"
    assert resultado.browser_verification_attempts == 2
