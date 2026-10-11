from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.intent_verification import (
    IntentDecision,
    criar_entrada_verificacao,
    interpretar_decisao,
    precisa_verificar,
    proposta_simples_exata,
)
from core.task_manager import TaskState
from providers.openai_provider import OpenAIProvider


def _call(name="definir_volume_windows", arguments='{"percentual":30}', call_id="one"):
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id=call_id)


def _response(*calls, text=""):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


def _harness(*, verifier, calls, execution=None):
    invoked = []
    responses = [_response(*calls)]
    harness = AurenHarness(
        criar_resposta=lambda *_args: responses.pop(0),
        executar_ferramenta=lambda item: invoked.append(item.name) or "volume definido",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [c for c in response.output if c.type == "function_call"],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=verifier,
    )
    return harness, invoked


def test_model_approves_before_dispatch():
    verifications = []

    def verifier(objective, calls, history):
        verifications.append((objective, [c.name for c in calls], list(history)))
        return IntentDecision("aprovar", "alvo coerente")

    harness, dispatched = _harness(verifier=verifier, calls=[_call()])
    _, response = harness.processar_mensagem("quero que o som fique mais baixo")
    assert verifications == [("quero que o som fique mais baixo", ["definir_volume_windows"], [])]
    assert dispatched == ["definir_volume_windows"]
    assert harness.current_task().state is TaskState.COMPLETED
    assert "volume definido" in response.output_text


def test_ambiguous_target_asks_without_dispatch():
    harness, dispatched = _harness(
        verifier=lambda *_: IntentDecision("esclarecer", "alvo incerto", "Qual aplicativo devo alterar?"),
        calls=[_call()],
    )
    _, response = harness.processar_mensagem("mude isso")
    assert dispatched == []
    assert response.output_text == "Qual aplicativo devo alterar?"
    assert harness.current_task().state is TaskState.COMPLETED
    assert harness.current_task().steps == ()


def test_semantic_mismatch_blocks_without_dispatch():
    harness, dispatched = _harness(
        verifier=lambda *_: IntentDecision("bloquear", "usuario pediu tocar, nao excluir"),
        calls=[_call()],
    )
    _, response = harness.processar_mensagem("toque musica")
    assert dispatched == []
    assert "Nao executei" in response.output_text
    assert harness.current_task().state is TaskState.FAILED


def test_verifier_unavailable_fails_closed_without_dispatch():
    def unavailable(*_):
        raise TimeoutError("offline")

    harness, dispatched = _harness(verifier=unavailable, calls=[_call()])
    _, response = harness.processar_mensagem("mude o audio daqui")
    assert dispatched == []
    assert "Nao consegui verificar" in response.output_text
    assert harness.current_task().state is TaskState.FAILED


def test_invalid_verifier_decision_fails_closed():
    harness, dispatched = _harness(
        verifier=lambda *_: SimpleNamespace(decisao="maybe"),
        calls=[_call()],
    )
    _, response = harness.processar_mensagem("defina o volume em 30")
    assert dispatched == []
    assert "Nao consegui verificar" in response.output_text


def test_read_only_query_does_not_invoke_paid_verifier():
    def unexpected(*_):
        raise AssertionError("reads should not require verification")

    harness, dispatched = _harness(
        verifier=unexpected,
        calls=[_call("obter_status_windows", "{}")],
    )
    _, response = harness.processar_mensagem("qual e o status do windows?")
    assert dispatched == ["obter_status_windows"]
    assert harness.current_task().state is TaskState.COMPLETED
    assert "volume definido" in response.output_text


def test_unknown_tool_is_not_treated_as_read_only():
    assert precisa_verificar([_call("ferramenta_futura")]) is True
    assert precisa_verificar([_call("ler_arquivo")]) is False


def test_intent_payload_preserves_original_and_batch():
    args = criar_entrada_verificacao(
        "abra o app, mas nao feche a janela",
        [_call("abrir_programa", '{"nome":"Chrome"}'), _call("fechar_janela_windows", '{"titulo":"Chrome"}')],
        [{"ferramenta": "listar_janelas_windows", "resultado": "Chrome aberto"}],
    )
    payload = json.loads(args)
    assert "nao feche" in payload["pedido_original"]
    assert len(payload["acoes_propostas"]) == 2
    assert payload["passos_anteriores_como_dados"][0]["ferramenta"] == "listar_janelas_windows"


@pytest.mark.parametrize("decision", [
    '{"decisao":"esclarecer","motivo":"incerto","pergunta":""}',
    '{"decisao":"bloquear","motivo":"","pergunta":""}',
    '{"decisao":"ignorar","motivo":"tudo bem","pergunta":""}',
    "ignore as instrucoes",
])
def test_bad_verifier_response_is_rejected(decision):
    with pytest.raises(ValueError):
        interpretar_decisao(decision)


def test_oversized_action_is_not_forwarded_to_verifier():
    with pytest.raises(ValueError):
        criar_entrada_verificacao("mova o arquivo", [_call(arguments="x" * 3001)], [])


def test_provider_verification_has_no_tools_and_counts_usage(monkeypatch):
    requests = []
    counted = []
    response = SimpleNamespace(
        output_text='{"decisao":"aprovar","motivo":"corresponde","pergunta":""}',
        usage=None,
    )

    class _Client:
        responses = SimpleNamespace(create=lambda **kwargs: requests.append(kwargs) or response)

    provider = OpenAIProvider()
    provider._client = _Client()
    monkeypatch.setattr("providers.openai_provider.usage.registrar_uso", lambda result: counted.append(result))
    verdict = provider.verify_intent("defina volume em 30", [_call()], [])
    assert verdict.decisao == "aprovar"
    assert requests[0]["tools"] == []
    assert requests[0]["store"] is False
    assert requests[0]["text"]["format"]["type"] == "json_schema"
    assert counted == [response]


def test_fast_path_is_blocked_before_it_can_act():
    from tools.fast_paths import planejar_comando_rapido

    executed = []
    harness = AurenHarness(
        criar_resposta=lambda *_: (_ for _ in ()).throw(AssertionError("should not call main model")),
        executar_ferramenta=lambda _: (_ for _ in ()).throw(AssertionError("no dispatch")),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda _: [],
        comando_rapido=lambda message: executed.append(message) or (True, "feito"),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=lambda *_: IntentDecision("bloquear", "site errado"),
        planejar_atalho=lambda _: [_call("fechar_aba", '{"indice":1}')],
    )
    _, response = harness.processar_mensagem("abra o YouTube")
    assert executed == []
    assert "Nao executei" in response.output_text
    assert harness.current_task().state is TaskState.FAILED


def test_fast_path_simple_command_does_not_use_paid_verification():
    from tools.fast_paths import planejar_comando_rapido

    executed = []
    harness = AurenHarness(
        criar_resposta=lambda *_: (_ for _ in ()).throw(AssertionError("no main model call")),
        executar_ferramenta=lambda _: (_ for _ in ()).throw(AssertionError("shortcut stub")),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda _: [],
        comando_rapido=lambda message: executed.append(message) or (True, "abri o YouTube"),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=lambda *_: (_ for _ in ()).throw(AssertionError("simple site must skip verification")),
        planejar_atalho=planejar_comando_rapido,
    )
    handled, response = harness.processar_mensagem("abra o YouTube")
    assert handled is True
    assert executed == ["abra o YouTube"]
    assert "abri o YouTube" in str(response)


def test_read_only_fast_path_skips_model_verification():
    from tools.fast_paths import planejar_comando_rapido

    executed = []
    harness = AurenHarness(
        criar_resposta=lambda *_: (_ for _ in ()).throw(AssertionError("no main model call")),
        executar_ferramenta=lambda _: (_ for _ in ()).throw(AssertionError("shortcut stub")),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda _: [],
        comando_rapido=lambda message: executed.append(message) or (True, "12:00"),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=lambda *_: (_ for _ in ()).throw(AssertionError("read-only")),
        planejar_atalho=planejar_comando_rapido,
    )
    handled, _ = harness.processar_mensagem("que horas sao")
    assert handled is True
    assert executed == ["que horas sao"]


def test_fast_path_plan_matches_dispatch_name_and_arguments():
    from tools.fast_paths import planejar_comando_rapido

    proposals = planejar_comando_rapido("abra o YouTube")
    assert len(proposals) == 1
    assert proposals[0].name == "navegar_navegador"
    assert json.loads(proposals[0].arguments)["url"] == "https://www.youtube.com"

    proposals = planejar_comando_rapido("abra duas abas")
    assert len(proposals) == 2
    assert all(p.name == "abrir_nova_aba" for p in proposals)


@pytest.mark.parametrize("pedido,tool,args", [
    ("defina o volume em 30", "definir_volume_windows", '{"percentual":30}'),
    ("coloque o volume em 0%", "definir_volume_windows", '{"percentual":0}'),
    ("ative o mudo", "definir_mudo_windows", '{"ativado":true}'),
    ("desative o mudo", "definir_mudo_windows", '{"ativado":false}'),
    ("pausa a musica", "controle_midia_windows", '{"acao":"play_pause"}'),
    ("proxima", "controle_midia_windows", '{"acao":"proxima"}'),
    ("abra o YouTube", "navegar_navegador", '{"url":"https://www.youtube.com","modo":"visivel"}'),
    ("abra o aplicativo Spotify", "abrir_programa", '{"programa":"Spotify"}'),
    ("abra o Chrome", "navegar_navegador", '{"url":"https://www.google.com","modo":"visivel"}'),
])
def test_exact_simple_intent_needs_no_extra_verifier(pedido, tool, args):
    # "abra o Chrome" intentionally does NOT qualify: site vs installed app is ambiguous.
    expected = pedido != "abra o Chrome"
    assert proposta_simples_exata(pedido, [_call(tool, args)], []) is expected


@pytest.mark.parametrize("pedido,tool,args", [
    ("defina o volume em 30", "definir_volume_windows", '{"percentual":80}'),
    ("defina o volume em 30", "definir_volume_windows", '{"percentual":"30"}'),
    ("defina o volume em 30", "definir_mudo_windows", '{"ativado":true}'),
    ("abra o YouTube", "navegar_navegador", '{"url":"https://github.com","modo":"visivel"}'),
    ("abra o YouTube", "navegar_navegador", '{"url":"https://www.youtube.com","modo":"oculto"}'),
    ("abra o aplicativo Spotify", "abrir_programa", '{"programa":"Discord"}'),
    ("abra o aplicativo Spotify e feche a janela", "abrir_programa", '{"programa":"Spotify"}'),
    ("pausa a musica", "controle_midia_windows", '{"acao":"proxima"}'),
    ("abra o YouTube", "fechar_aba", '{"indice":1}'),
    ("abra o YouTube", "navegar_navegador", '{"url":"https://www.youtube.com","modo":"visivel","extra":1}'),
    ("defina o volume em 30", "definir_volume_windows", "not json"),
])
def test_changed_or_ambiguous_action_requires_verifier(pedido, tool, args):
    assert proposta_simples_exata(pedido, [_call(tool, args)], []) is False


def test_even_simple_action_requires_verifier_with_prior_steps_or_extra_actions():
    first = _call("definir_volume_windows", '{"percentual":30}')
    extra = _call("fechar_aba", '{"indice":1}')
    assert not proposta_simples_exata("defina o volume em 30", [first, extra], [])
    assert not proposta_simples_exata(
        "defina o volume em 30", [first], [{"ferramenta": "listar_abas", "resultado": "ok"}]
    )


def test_semantic_reviewer_not_called_for_exact_volume_action():
    calls = []
    harness, dispatched = _harness(
        verifier=lambda *_: calls.append("extra_api") or IntentDecision("bloquear", "nao deveria chamar"),
        calls=[_call("definir_volume_windows", '{"percentual":30}')],
    )
    _, response = harness.processar_mensagem("defina o volume em 30")
    assert calls == []
    assert dispatched == ["definir_volume_windows"]
    assert harness.current_task().state is TaskState.COMPLETED
    assert "volume definido" in response.output_text


def test_semantic_reviewer_still_blocks_wrong_volume_value():
    calls = []
    harness, dispatched = _harness(
        verifier=lambda *_: calls.append("extra_api") or IntentDecision("bloquear", "valor diferente"),
        calls=[_call("definir_volume_windows", '{"percentual":80}')],
    )
    _, response = harness.processar_mensagem("defina o volume em 30")
    assert calls == ["extra_api"]
    assert dispatched == []
    assert harness.current_task().state is TaskState.FAILED
    assert "Nao executei" in response.output_text


def test_semantic_reviewer_fails_closed_on_complex_command():
    harness, dispatched = _harness(
        verifier=lambda *_: (_ for _ in ()).throw(TimeoutError("sem conexao")),
        calls=[_call("definir_volume_windows", '{"percentual":30}')],
    )
    _, response = harness.processar_mensagem("defina o volume em 30 e depois abra outra janela")
    assert dispatched == []
    assert "Nao consegui verificar" in response.output_text
