
from types import SimpleNamespace

from core.harness_guards import _tratar_rodada_sem_ferramentas


class _TaskManager:
    def __init__(self):
        self.events = []

    def wait_for_model(self, task_id):
        self.events.append(("wait", task_id))

    def resume(self, task_id):
        self.events.append(("resume", task_id))


def _resposta(texto):
    return SimpleNamespace(output_text=texto, output=[])


def _base_callbacks(events, respostas=None):
    respostas = list(respostas or [_resposta("nova resposta")])

    def montar_estado(objetivo, historico, resultado):
        events.append(("montar_estado", objetivo, historico, resultado))
        return "estado de retry"

    def pedir_modelo(estado, tool_choice):
        events.append(("pedir_modelo", estado, tool_choice))
        resposta = respostas.pop(0)
        return resposta, 12.345, {"rota": "teste"}

    def log_resposta(*args, **kwargs):
        events.append(("log_resposta", args, kwargs))

    return montar_estado, pedir_modelo, log_resposta


def test_action_retry_on_first_round_requires_tool():
    events = []
    montar_estado, pedir_modelo, log_resposta = _base_callbacks(
        events,
        [_resposta("agora sim")]
    )

    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="abra o navegador",
        historico=[],
        rodada=1,
        exigir_ferramenta=True,
        ferramentas_executadas=0,
        resposta=_resposta("sem ferramenta"),
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-1",
        task_manager=_TaskManager(),
        montar_estado=montar_estado,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
    )

    assert resultado.acao == "continuar"
    assert resultado.resposta.output_text == "agora sim"
    assert resultado.vision_guard_attempts == 0
    assert resultado.multitab_guard_attempts == 0
    assert events[0][0] == "montar_estado"
    assert events[1][0] == "write_log"
    assert events[2] == ("pedir_modelo", "estado de retry", "required")
    assert events[3][0] == "log_resposta"


def test_action_requested_but_never_executed_returns_failure():
    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="clique em salvar",
        historico=[],
        rodada=2,
        exigir_ferramenta=True,
        ferramentas_executadas=0,
        resposta=_resposta("nada"),
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-2",
        task_manager=_TaskManager(),
        montar_estado=lambda *args: "unused",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: None,
    )

    assert resultado.acao == "falhar"
    assert resultado.failure_code == "action_not_executed"
    assert resultado.failure_message == "Nao consegui executar a acao solicitada."


def test_visual_guard_retries_and_updates_counter():
    events = []
    manager = _TaskManager()
    montar_estado, pedir_modelo, log_resposta = _base_callbacks(
        events,
        [_resposta("verifiquei")]
    )

    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="abra a janela",
        historico=[],
        rodada=3,
        exigir_ferramenta=False,
        ferramentas_executadas=1,
        resposta=_resposta("aguardando"),
        vision_reobserve_pending=True,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-3",
        task_manager=manager,
        montar_estado=montar_estado,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
    )

    assert resultado.acao == "continuar"
    assert resultado.vision_guard_attempts == 1
    assert resultado.resposta.output_text == "verifiquei"
    assert manager.events == [("wait", "task-3"), ("resume", "task-3")]
    assert any(item[0] == "write_log" and item[1][0] == "TASK_VISUAL_GUARD" for item in events)


def test_visual_guard_exhaustion_returns_failure():
    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="abra a janela",
        historico=[],
        rodada=4,
        exigir_ferramenta=False,
        ferramentas_executadas=1,
        resposta=_resposta("aguardando"),
        vision_reobserve_pending=True,
        vision_guard_attempts=2,
        multitab_guard_attempts=0,
        task_id="task-4",
        task_manager=_TaskManager(),
        montar_estado=lambda *args: "unused",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: None,
    )

    assert resultado.acao == "falhar"
    assert resultado.failure_code == "visual_verification_missing"


def test_multitab_guard_retries_and_updates_counter():
    events = []
    manager = _TaskManager()
    montar_estado, pedir_modelo, log_resposta = _base_callbacks(
        events,
        [_resposta("continuei")]
    )

    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="coloque os destinos nas abas 1 e 2",
        historico=[],
        rodada=5,
        exigir_ferramenta=False,
        ferramentas_executadas=2,
        resposta=_resposta("aguardando"),
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=1,
        task_id="task-5",
        task_manager=manager,
        montar_estado=montar_estado,
        pedir_modelo=pedir_modelo,
        log_resposta_modelo=log_resposta,
        parece_tarefa_multietapa_browser=lambda _: True,
        extrair_destinos_abas=lambda _: {1: "a", 2: "b"},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: events.append(("write_log", args, kwargs)),
    )

    assert resultado.acao == "continuar"
    assert resultado.multitab_guard_attempts == 2
    assert manager.events == [("wait", "task-5"), ("resume", "task-5")]
    assert any(item[0] == "write_log" and item[1][0] == "TASK_MULTITAB_GUARD" for item in events)


def test_provider_failure_returns_directly_without_re_failing_task():
    manager = _TaskManager()

    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="abra o navegador",
        historico=[],
        rodada=3,
        exigir_ferramenta=False,
        ferramentas_executadas=1,
        resposta=_resposta("aguardando"),
        vision_reobserve_pending=True,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-6",
        task_manager=manager,
        montar_estado=lambda *args: "estado",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: None,
    )

    assert resultado.acao == "retornar"
    assert resultado.resposta == "Tive um problema ao acessar o modelo. A tarefa nao foi concluida."
    assert resultado.vision_guard_attempts == 1
    assert manager.events == [("wait", "task-6")]


def test_without_any_guard_condition_proceeds_with_current_response():
    resposta = _resposta("final")
    resultado = _tratar_rodada_sem_ferramentas(
        objetivo="como esta o tempo?",
        historico=[],
        rodada=2,
        exigir_ferramenta=False,
        ferramentas_executadas=0,
        resposta=resposta,
        vision_reobserve_pending=False,
        vision_guard_attempts=0,
        multitab_guard_attempts=0,
        task_id="task-7",
        task_manager=_TaskManager(),
        montar_estado=lambda *args: "unused",
        pedir_modelo=lambda *args: None,
        log_resposta_modelo=lambda *args, **kwargs: None,
        parece_tarefa_multietapa_browser=lambda _: False,
        extrair_destinos_abas=lambda _: {},
        multitab_concluida=lambda *_: False,
        write_log=lambda *args, **kwargs: None,
    )

    assert resultado.acao == "prosseguir"
    assert resultado.resposta is resposta



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
