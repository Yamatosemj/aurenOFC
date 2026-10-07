from __future__ import annotations

from types import SimpleNamespace

from core.harness_completion import _finalizar_resposta_sucesso


class _TaskManager:
    def __init__(self, snapshot=None):
        self.completed = []
        self.snapshot = snapshot

    def complete(self, texto, *, task_id):
        self.completed.append((texto, task_id))

    def current_snapshot(self):
        return self.snapshot


def _resposta(texto):
    return SimpleNamespace(output_text=texto, output=[])


def test_finaliza_resposta_preserva_resposta_e_completa_tarefa():
    resposta = _resposta("resposta final")
    manager = _TaskManager(SimpleNamespace(state=SimpleNamespace(value="completed")))
    saved = []
    turns = []
    logs = []

    resultado = _finalizar_resposta_sucesso(
        "objetivo",
        [],
        resposta,
        apos_tarefa=None,
        task_id="task-1",
        salvar_estrategia=lambda *args: saved.append(args),
        task_manager=manager,
        registrar_turno=lambda *args: turns.append(args),
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
        criar_resposta=_resposta,
    )

    assert resultado is resposta
    assert saved == [("objetivo", [], "resposta final", True)]
    assert manager.completed == [("resposta final", "task-1")]
    assert turns == [("assistant", "resposta final")]
    assert logs == [
        (("TASK_STATE",), {"task_id": "task-1", "estado": "completed"})
    ]


def test_finaliza_resposta_anexa_extra_de_apos_tarefa():
    resposta = _resposta("resposta")
    historico = [{"ferramenta": "abrir", "resultado": "ok"}]
    manager = _TaskManager(SimpleNamespace(state=SimpleNamespace(value="completed")))
    callback_calls = []

    resultado = _finalizar_resposta_sucesso(
        "objetivo",
        historico,
        resposta,
        apos_tarefa=lambda objetivo, historico: (
            callback_calls.append((objetivo, historico)) or " | memoria salva"
        ),
        task_id="task-2",
        salvar_estrategia=lambda objetivo, historico, texto, sucesso: callback_calls.append(
            ("save", objetivo, historico, texto, sucesso)
        ),
        task_manager=manager,
        registrar_turno=lambda papel, texto: callback_calls.append(("turn", papel, texto)),
        write_log=lambda *args, **kwargs: callback_calls.append(("log", args, kwargs)),
        criar_resposta=_resposta,
    )

    assert resultado.output_text == "resposta | memoria salva"
    assert callback_calls[0] == ("objetivo", historico)
    assert callback_calls[1] == ("save", "objetivo", historico, "resposta | memoria salva", True)
    assert manager.completed == [("resposta | memoria salva", "task-2")]


def test_erro_de_apos_tarefa_apenas_registra_memoria_e_conclui():
    resposta = _resposta("resposta")
    historico = [{"ferramenta": "abrir", "resultado": "ok"}]
    manager = _TaskManager(None)
    logs = []

    def falhar(*_args):
        raise RuntimeError("memoria indisponivel")

    _finalizar_resposta_sucesso(
        "objetivo",
        historico,
        resposta,
        apos_tarefa=falhar,
        task_id="task-3",
        salvar_estrategia=lambda *args: None,
        task_manager=manager,
        registrar_turno=lambda *args: None,
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
        criar_resposta=_resposta,
    )

    assert logs == [
        (
            ("MEMORY_ERROR",),
            {"task_id": "task-3", "erro": "memoria indisponivel"},
        ),
        (
            ("TASK_STATE",),
            {"task_id": "task-3", "estado": "completed"},
        ),
    ]
    assert manager.completed == [("resposta", "task-3")]


from core.harness_completion import _tentar_retry_resposta_vazia


class _EmptyResponseTaskManager:
    def __init__(self):
        self.events = []

    def wait_for_model(self, task_id):
        self.events.append(("wait", task_id))

    def resume(self, task_id):
        self.events.append(("resume", task_id))


def _resposta_vazia_test(texto):
    return SimpleNamespace(output_text=texto, output=[])


def test_retry_resposta_vazia_executa_nova_rodada_e_retorna_continuar():
    events = []
    manager = _EmptyResponseTaskManager()

    def montar_estado(objetivo, historico, resultado):
        events.append(("estado", objetivo, historico, resultado))
        return "estado retry"

    def pedir_modelo(estado, tool_choice):
        events.append(("modelo", estado, tool_choice))
        return _resposta_vazia_test("agora existe resposta"), 12.345, {"rota": "teste"}

    def log_resposta(*args, **kwargs):
        events.append(("log_resposta", args, kwargs))

    result = _tentar_retry_resposta_vazia(
        "objetivo",
        [],
        rodada=2,
        exigir_ferramenta=True,
        empty_response_retries=0,
        task_id="task-1",
        mensagem_erro_provider="provider erro",
        task_manager=manager,
        montar_estado=montar_estado,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        write_log=lambda *args, **kwargs: events.append(("log", args, kwargs)),
        should_cancel=lambda _: False,
        encerrar_cancelado=lambda *args: ("cancelado", args),
        criar_resposta=_resposta_vazia_test,
    )

    assert result.acao == "continuar"
    assert result.empty_response_retries == 1
    assert result.resposta.output_text == "agora existe resposta"
    assert manager.events == [("wait", "task-1"), ("resume", "task-1")]
    assert events[0] == (
        "estado",
        "objetivo",
        [],
        [{
            "ferramenta": "nenhuma",
            "argumentos": "{}",
            "resultado": "A resposta final veio vazia. Responda de forma objetiva ou continue a execucao necessaria.",
        }],
    )
    model_event = next(item for item in events if item[0] == "modelo")
    log_event = next(item for item in events if item[0] == "log")
    response_log = next(item for item in events if item[0] == "log_resposta")
    assert model_event == ("modelo", "estado retry", "required")
    assert log_event[1][0] == "MODEL_ROUND_REQUEST"
    assert log_event[2]["rodada"] == 3
    assert log_event[2]["motivo"] == "empty_response_retry"
    assert response_log[1][-1]["motivo"] == "empty_response_retry"


def test_retry_resposta_vazia_cancela_antes_de_esperar_modelo():
    manager = _EmptyResponseTaskManager()
    result = _tentar_retry_resposta_vazia(
        "objetivo",
        [],
        rodada=4,
        exigir_ferramenta=False,
        empty_response_retries=0,
        task_id="task-2",
        mensagem_erro_provider="provider erro",
        task_manager=manager,
        montar_estado=lambda *args: "estado",
        pedir_modelo=lambda *args: (_resposta_vazia_test("nao deveria"), 1.0, {}),
        log_resposta_modelo=lambda *args, **kwargs: None,
        write_log=lambda *args, **kwargs: None,
        should_cancel=lambda _: True,
        encerrar_cancelado=lambda *args: ("cancelado", args),
        criar_resposta=_resposta_vazia_test,
    )
    assert result.acao == "retornar"
    assert result.empty_response_retries == 1
    assert result.resposta == (
        "cancelado",
        ("cancelado antes do retry de resposta vazia", 4),
    )
    assert manager.events == []


def test_retry_resposta_vazia_provider_failure_retorna_sem_resume():
    manager = _EmptyResponseTaskManager()
    result = _tentar_retry_resposta_vazia(
        "objetivo",
        [],
        rodada=3,
        exigir_ferramenta=False,
        empty_response_retries=0,
        task_id="task-3",
        mensagem_erro_provider="provider erro",
        task_manager=manager,
        montar_estado=lambda *args: "estado",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        write_log=lambda *args, **kwargs: None,
        should_cancel=lambda _: False,
        encerrar_cancelado=lambda *args: ("cancelado", args),
        criar_resposta=_resposta_vazia_test,
    )
    assert result.acao == "retornar"
    assert result.resposta.output_text == "provider erro"
    assert result.empty_response_retries == 1
    assert manager.events == [("wait", "task-3")]


def test_retry_resposta_vazia_exaurido_nao_chama_modelo():
    result = _tentar_retry_resposta_vazia(
        "objetivo",
        [],
        rodada=5,
        exigir_ferramenta=True,
        empty_response_retries=1,
        task_id="task-4",
        mensagem_erro_provider="provider erro",
        task_manager=_EmptyResponseTaskManager(),
        montar_estado=lambda *args: (_ for _ in ()).throw(AssertionError("nao deveria montar retry")),
        pedir_modelo=lambda *args: (_ for _ in ()).throw(AssertionError("nao deveria chamar provider")),
        log_resposta_modelo=lambda *args, **kwargs: None,
        write_log=lambda *args, **kwargs: None,
        should_cancel=lambda _: False,
        encerrar_cancelado=lambda *args: ("cancelado", args),
        criar_resposta=_resposta_vazia_test,
    )
    assert result.acao == "falhar"
    assert result.empty_response_retries == 1
    assert result.failure_code == "empty_response"
    assert result.failure_message == "Nao consegui produzir uma resposta final."
