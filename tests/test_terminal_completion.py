from core.harness import AurenHarness
from core.task_manager import TaskState
from core.tool_result import ToolResult


def _item(name, result, success=True):
    return {
        "call_id": "call-1",
        "ferramenta": name,
        "argumentos": "{}",
        "resultado": result,
        "sucesso": success,
    }


def test_leitura_terminal_pula_rodada_extra():
    itens = [_item("obter_audio_windows", "Volume atual: 37%. Mudo: desativado.")]
    assert AurenHarness._pode_encerrar_localmente("qual o volume do sistema?", itens)
    assert (
        AurenHarness._mensagem_conclusao_local(
            "qual o volume do sistema?",
            "obter_audio_windows",
            itens[0]["resultado"],
        )
        == "Volume atual: 37%. Mudo: desativado."
    )


def test_leitura_nao_encerra_tarefa_de_acao_so_com_preflight():
    itens = [_item("obter_audio_windows", "Volume atual: 37%. Mudo: desativado.")]
    assert not AurenHarness._pode_encerrar_localmente("defina o volume para 50%", itens)


def test_acao_terminal_simples_pula_rodada_extra():
    itens = [_item("definir_volume_windows", "Volume definido para 50%.")]
    assert AurenHarness._pode_encerrar_localmente("defina o volume para 50%", itens)
    assert (
        AurenHarness._mensagem_conclusao_local(
            "defina o volume para 50%",
            "definir_volume_windows",
            itens[0]["resultado"],
        )
        == "Volume definido para 50%."
    )


def test_falha_terminal_nao_encerra_localmente():
    itens = [_item(
        "definir_volume_windows",
        '{"ok":false,"mensagem":"Volume invalido."}',
        success=False,
    )]
    assert not AurenHarness._pode_encerrar_localmente("defina o volume para 150%", itens)


def test_spotify_playback_nao_encerra_com_listagem_de_janelas():
    itens = [_item("listar_janelas_windows", "Janelas visiveis: 19\n2. Spotify Premium [ATIVA]")]
    assert not AurenHarness._pode_encerrar_localmente(
        "Auren, toca Evidências no Spotify",
        itens,
    )


def test_inspecao_uia_nao_encerra_com_preflight_de_janelas():
    itens = [_item("listar_janelas_windows", "Janelas visiveis: 25")]
    assert not AurenHarness._pode_encerrar_localmente(
        "inspecione a interface da janela AUREN_UIA_TESTE procurando Campo de Teste",
        itens,
    )


def test_listar_abas_nao_e_terminal_em_tarefa_multietapa():
    itens = [_item("listar_abas", "Abas abertas: 3\nAba 1: GitHub\nAba 2: sobre:blank\nAba 3: sobre:blank")]
    assert not AurenHarness._pode_encerrar_localmente(
        "abra o discord na segunda aba e o youtube na terceira aba",
        itens,
    )


def test_multitab_estado_real_confirma_destinos_conhecidos():
    historico = [
        _item(
            "listar_abas",
            "Abas abertas: 3\n"
            "Aba 1: GitHub | https://github.com\n"
            "Aba 2: Discord | https://discord.com/app\n"
            "Aba 3: YouTube | https://www.youtube.com/",
        )
    ]
    objetivo = "abra o discord na segunda aba e o youtube na terceira aba"
    assert AurenHarness._multitab_concluida(objetivo, historico)


def test_multitab_estado_real_nao_confirma_destino_incompleto():
    historico = [
        _item(
            "listar_abas",
            "Abas abertas: 3\n"
            "Aba 1: GitHub | https://github.com\n"
            "Aba 2: Discord | https://discord.com/app\n"
            "Aba 3: sobre:blank | chrome://newtab",
        )
    ]
    objetivo = "abra o discord na segunda aba e o youtube na terceira aba"
    assert not AurenHarness._multitab_concluida(objetivo, historico)


def test_multitab_listagem_final_pode_encerrar_localmente():
    itens = [
        _item(
            "listar_abas",
            "Abas abertas: 3\n"
            "Aba 1: GitHub | https://github.com\n"
            "Aba 2: Discord | https://discord.com/app\n"
            "Aba 3: YouTube | https://www.youtube.com/",
        )
    ]
    objetivo = "abra o discord na segunda aba e o youtube na terceira aba"
    assert AurenHarness._pode_encerrar_localmente(objetivo, itens)
    assert "verificadas com sucesso" in AurenHarness._mensagem_conclusao_local(
        objetivo, "listar_abas", itens[0]["resultado"]
    )




def _make_harness(responses, executor=None, max_rounds=3):
    from types import SimpleNamespace
    from core.task_manager import TaskManager

    class FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text
            self.usage = None

    queue_responses = list(responses)
    def criar_resposta(*_args, **_kwargs):
        value = queue_responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=executor or (lambda _item: "ok"),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [item for item in response.output if getattr(item, "type", "") == "function_call"],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=TaskManager(),
        max_model_rounds=max_rounds,
    )
    return harness, FakeResponse, SimpleNamespace


def test_acao_sem_tool_apos_retry_falha():
    _, Response, _ = _make_harness([])
    harness, _, _ = _make_harness([Response([], "Nao posso fazer isso"), Response([], "Ainda nao executei")])
    tratado, resposta = harness.processar_mensagem("abra o notepad")
    assert tratado is False
    assert resposta.output_text == "Nao consegui executar a acao solicitada."
    snapshot = harness.current_task()
    assert snapshot.state is TaskState.FAILED
    assert snapshot.error == "action_not_executed"
    assert snapshot.steps == ()


def test_resposta_vazia_faz_um_retry_e_depois_falha():
    _, Response, _ = _make_harness([])
    harness, _, _ = _make_harness([Response([], ""), Response([], "")])
    tratado, resposta = harness.processar_mensagem("oi")
    assert tratado is False
    assert resposta.output_text == "Nao consegui produzir uma resposta final."
    assert harness.current_task().error == "empty_response"


def test_resposta_vazia_seguida_de_texto_completa():
    _, Response, _ = _make_harness([])
    harness, _, _ = _make_harness([Response([], ""), Response([], "Tudo certo.")])
    tratado, resposta = harness.processar_mensagem("oi")
    assert tratado is False
    assert resposta.output_text == "Tudo certo."
    assert harness.current_task().state is TaskState.COMPLETED


def test_step_failure_sem_recovery_falha_tarefa():
    from types import SimpleNamespace
    _, Response, _ = _make_harness([])
    harness, _, _ = _make_harness([
        Response([SimpleNamespace(type="function_call", name="definir_volume_windows", arguments='{"percentual":150}', call_id="1")]),
        Response([], "Nao foi possivel."),
    ], executor=lambda _item: ToolResult.failure("erro", error_code="test_failure", tool_name="definir_volume_windows"))
    tratado, resposta = harness.processar_mensagem("defina o volume para 150%")
    assert tratado is False
    assert "etapa falhou" in resposta.output_text
    assert harness.current_task().state is TaskState.FAILED
    assert harness.current_task().steps[0].success is False


def test_falha_ao_abrir_nao_e_recuperada_por_consultar_status():
    from types import SimpleNamespace
    _, Response, _ = _make_harness([])
    outputs = [
        SimpleNamespace(type="function_call", name="abrir_programa", arguments='{"programa":"Notepad"}', call_id="1"),
        SimpleNamespace(type="function_call", name="obter_status_windows", arguments="{}", call_id="2"),
    ]
    results = [
        ToolResult.failure("falhou", error_code="test_failure", tool_name="abrir_programa"),
        ToolResult.success("recuperado", data={}),
    ]
    idx = {"i": 0}
    def executor(_item):
        value = results[idx["i"]]
        idx["i"] += 1
        return value
    harness, _, _ = _make_harness([Response([outputs[0], outputs[1]]), Response([], "recuperado com sucesso")], executor=executor)
    harness.processar_mensagem("abra o Notepad e depois verifique o status do sistema")
    snap = harness.current_task()
    # Consultar o status nao abriu o Notepad; o teste anterior tratava esse
    # sucesso como "recovery" mesmo sem reparar a operacao que falhou.
    assert snap.state is TaskState.FAILED
    assert snap.error == "step_failed_unrecovered"
    assert len(snap.steps) == 2
    assert snap.steps[0].success is False
    assert snap.steps[1].success is True
