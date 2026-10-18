"""Continuidade de reasoning entre rodadas do Harness, totalmente offline.

O default de esforco 'none' NAO muda. Estes testes validam o transporte
dos itens recebidos, nao raciocinio real do modelo/API.
"""
from __future__ import annotations

from types import SimpleNamespace

from core.harness_round_input import (
    _montar_input_da_rodada,
    _montar_input_e_estado_da_rodada,
)
from providers.openai_provider import OpenAIProvider


def _build(response, results, *, history=None):
    states = []
    updated = []
    def make_state(objective, previous, incluir_contexto):
        states.append((objective, previous, incluir_contexto))
        return "estado limitado"

    items, state = _montar_input_e_estado_da_rodada(
        "objetivo",
        history or [],
        response,
        results,
        montar_estado=make_state,
        preparar_resultado_visual=lambda _result: None,
        ao_atualizar_geometria=lambda: updated.append(True),
    )
    assert state == "estado limitado"
    assert updated == []
    return items, states


def test_reasoning_and_calls_from_only_previous_response_are_kept_in_order():
    reasoning = SimpleNamespace(type="reasoning", id="rs_1", summary=[{"text": "resumo"}], encrypted_content="cipher")
    call = SimpleNamespace(type="function_call", id="fc_1", call_id="c1", name="listar_janelas_windows", arguments="{}")
    message = SimpleNamespace(type="message", id="msg_1", content=[{"text": "nao reenviar"}])
    second_reasoning = SimpleNamespace(type="reasoning", id="rs_2", summary=[])
    second_call = SimpleNamespace(type="function_call", id="fc_2", call_id="c2", name="obter_status_windows", arguments="{}")
    response = SimpleNamespace(output=[reasoning, call, message, second_reasoning, second_call])
    results = [{"call_id": "c1", "resultado": "janelas"}, {"call_id": "c2", "resultado": "status"}]
    history = [
        {"ferramenta": "antiga", "resultado": "anterior"},
        {"ferramenta": "listar_janelas_windows", "resultado": "janelas"},
        {"ferramenta": "obter_status_windows", "resultado": "status"},
    ]

    items, states = _build(response, results, history=history)
    assert states == [("objetivo", history[:1], True)]
    assert items[0]["role"] == "user"
    # Objetos e conteudo originais sao preservados para o SDK;
    # mensagens finais nao entram no input de continuacao.
    assert items[1:5] == [reasoning, call, second_reasoning, second_call]
    assert all(items[i] is obj for i, obj in enumerate(
        [reasoning, call, second_reasoning, second_call], start=1
    ))
    assert items[5:] == [
        {"type": "function_call_output", "call_id": "c1", "output": "janelas"},
        {"type": "function_call_output", "call_id": "c2", "output": "status"},
    ]
    assert message not in items


def test_without_reasoning_keeps_legacy_function_call_output_contract():
    call = SimpleNamespace(type="function_call", call_id="one")
    inputs, _ = _build(
        SimpleNamespace(output=[call]),
        [{"call_id": "one", "resultado": "ok"}],
    )
    assert inputs[1] is call
    assert inputs[2] == {"type": "function_call_output", "call_id": "one", "output": "ok"}
    assert len(inputs) == 3


def test_empty_output_and_none_response_are_accepted():
    for response in [None, SimpleNamespace(output=None), SimpleNamespace(output=[])]:
        inputs, _ = _build(response, [{"call_id": "one", "resultado": "erro"}])
        assert len(inputs) == 2
        assert inputs[1]["type"] == "function_call_output"


def test_no_reasoning_from_older_rounds_is_repeated():
    old_reasoning = SimpleNamespace(type="reasoning", id="old")
    prior = SimpleNamespace(type="reasoning", id="current")
    current_call = SimpleNamespace(type="function_call", call_id="c")
    inputs, _ = _build(
        SimpleNamespace(output=[prior, current_call]),
        [{"call_id": "c", "resultado": "ok"}],
        history=[{"ferramenta": "de_outra_rodada", "resultado": str(old_reasoning)}],
    )
    assert inputs[1:3] == [prior, current_call]
    assert old_reasoning not in inputs


def test_followup_provider_receives_reasoning_unchanged_and_no_previous_response_id():
    reasoning = SimpleNamespace(type="reasoning", id="rs_1", encrypted_content="encrypted")
    call = SimpleNamespace(type="function_call", call_id="c1")
    items = _montar_input_da_rodada(
        "objetivo",
        [],
        SimpleNamespace(output=[reasoning, call]),
        [{"call_id": "c1", "resultado": "ok"}],
        montar_estado=lambda *_args, **_kwargs: "estado",
        preparar_resultado_visual=lambda _item: None,
        ao_atualizar_geometria=lambda: None,
    )
    requests = []
    provider = OpenAIProvider()
    provider._client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: (
            requests.append(kwargs) or SimpleNamespace(usage=None, output=[], output_text="concluido")
        ))
    )
    response = provider.create_response(items, reasoning_effort="none", tools=[])
    assert response.output_text == "concluido"
    assert len(requests) == 1
    sent = requests[0]
    assert sent["input"] is items
    assert sent["input"][1] is reasoning
    assert sent["input"][2] is call
    assert sent["reasoning"] == {"effort": "none"}
    assert sent["tools"] == []
    assert "previous_response_id" not in sent
