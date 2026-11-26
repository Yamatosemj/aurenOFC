"""Contabilizacao offline de rodadas, chamadas ao provider e cache local."""

from __future__ import annotations

import json
from types import SimpleNamespace

from core.harness import AurenHarness
from core.orchestrator import _CachedResponse
from core.task_trace import TaskTraceStore
from core import usage
from core.usage import calcular_custo_estimado
from providers.openai_provider import OpenAIProvider


def _usage(input_tokens: int, output_tokens: int):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0))


def _response(*, text="", calls=(), usage=None, model="gpt-5.6-luna"):
    return SimpleNamespace(output=list(calls), output_text=text, usage=usage, model=model)


def _provider(*responses):
    provider = OpenAIProvider()
    pending = list(responses)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        result = pending.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    return provider, calls


def _harness(store, create_response, *, verifier=None):
    return AurenHarness(
        criar_resposta=create_response,
        executar_ferramenta=lambda _item: "volume definido",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [item for item in response.output
                                       if item.type == "function_call"],
        comando_rapido=lambda _message: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=verifier,
        trace_store=store,
    )


def test_main_response_and_semantic_verification_are_distinct_provider_calls(tmp_path, monkeypatch):
    for name in ("session_input_tokens", "session_output_tokens", "session_cached_tokens",
                 "session_cache_write_tokens", "session_cost", "session_cost_known_calls",
                 "session_cost_unknown_calls"):
        monkeypatch.setattr(usage, name, 0)
    tool = SimpleNamespace(type="function_call", name="definir_volume_windows",
                           arguments='{"percentual":30}', call_id="call-1")
    provider, sdk_calls = _provider(
        _response(calls=[tool], usage=_usage(100, 10)),
        _response(text=json.dumps({"decisao": "aprovar", "motivo": "coerente", "pergunta": ""}),
                  usage=_usage(20, 5)),
    )
    store = TaskTraceStore(tmp_path / "calls.sqlite3")
    harness = _harness(store, lambda entrada, *_: provider.create_response(entrada, tools=[]),
                       verifier=provider.verify_intent)

    _, answer = harness.processar_mensagem("quero que o som fique mais baixo")
    task_id = harness.current_task().task_id
    row = store.get_task(task_id)
    provider_spans = [span for span in store.get_spans(task_id) if span["category"] == "provider"]

    assert "volume definido" in answer.output_text
    assert len(sdk_calls) == 2
    assert row["model_rounds"] == 1
    assert (row["input_tokens"], row["output_tokens"]) == (120, 15)
    assert (usage.session_input_tokens, usage.session_output_tokens) == (120, 15)
    assert row["cost_usd"] == (
        calcular_custo_estimado({"input_tokens": 100, "output_tokens": 10}, "gpt-5.6-luna")
        + calcular_custo_estimado({"input_tokens": 20, "output_tokens": 5}, "gpt-5.6-luna")
    )
    assert row["cost_status"] == "estimated"
    assert row["cost_usd"] == usage.session_cost
    assert (row["cost_known_calls"], row["cost_unknown_calls"]) == (2, 0)
    assert [(span["name"], span["success"]) for span in provider_spans] == [
        ("response", 1), ("verification", 1),
    ]
    assert [json.loads(span["metadata_json"])["input_tokens"] for span in provider_spans] == [100, 20]
    assert all(span["duration_ms"] >= 0 for span in provider_spans)


def test_failed_provider_attempt_is_visible_without_invented_usage(tmp_path):
    provider, sdk_calls = _provider(RuntimeError("offline"))
    store = TaskTraceStore(tmp_path / "failed.sqlite3")
    harness = _harness(store, lambda entrada, *_: provider.create_response(entrada, tools=[]))

    harness.processar_mensagem("explique este conceito")
    task_id = harness.current_task().task_id
    row = store.get_task(task_id)
    provider_spans = [span for span in store.get_spans(task_id) if span["category"] == "provider"]

    assert len(sdk_calls) == 1
    assert row["status"] == "failed"
    assert row["model_rounds"] == 0
    assert len(provider_spans) == 1
    assert provider_spans[0]["name"] == "response"
    assert provider_spans[0]["success"] == 0
    assert json.loads(provider_spans[0]["metadata_json"])["usage_available"] is False
    assert row["cost_status"] == "unknown"


def test_successful_provider_response_without_usage_is_marked_unavailable(tmp_path):
    provider, _ = _provider(_response(text="ok", usage=None))
    store = TaskTraceStore(tmp_path / "missing-usage.sqlite3")
    harness = _harness(store, lambda entrada, *_: provider.create_response(entrada, tools=[]))

    harness.processar_mensagem("explique este conceito")
    task_id = harness.current_task().task_id
    provider_span = next(span for span in store.get_spans(task_id) if span["category"] == "provider")

    assert provider_span["success"] == 1
    assert json.loads(provider_span["metadata_json"])["usage_available"] is False
    assert json.loads(provider_span["metadata_json"])["cost_status"] == "unknown"
    assert store.get_task(task_id)["cost_status"] == "unknown"


def test_local_cache_hit_counts_as_harness_round_without_provider_call(tmp_path):
    store = TaskTraceStore(tmp_path / "cache.sqlite3")
    harness = _harness(store, lambda *_: _CachedResponse("resposta em cache", "key"))

    _, response = harness.processar_mensagem("explique este conceito")
    task_id = harness.current_task().task_id
    row = store.get_task(task_id)
    spans = store.get_spans(task_id)

    assert response.output_text == "resposta em cache"
    assert row["model_rounds"] == 1
    assert row["input_tokens"] == row["output_tokens"] == 0
    assert [span for span in spans if span["category"] == "provider"] == []
    assert len([span for span in spans if span["category"] == "local_cache"]) == 1
    assert row["cost_status"] == "zero"


def test_failed_semantic_verification_preserves_main_usage_and_records_attempt(tmp_path):
    tool = SimpleNamespace(type="function_call", name="definir_volume_windows",
                           arguments='{"percentual":30}', call_id="call-1")
    provider, sdk_calls = _provider(
        _response(calls=[tool], usage=_usage(100, 10)), RuntimeError("verification offline"),
    )
    store = TaskTraceStore(tmp_path / "verification-failed.sqlite3")
    harness = _harness(store, lambda entrada, *_: provider.create_response(entrada, tools=[]),
                       verifier=provider.verify_intent)

    harness.processar_mensagem("quero que o som fique mais baixo")
    task_id = harness.current_task().task_id
    row = store.get_task(task_id)
    provider_spans = [span for span in store.get_spans(task_id) if span["category"] == "provider"]

    assert len(sdk_calls) == 2
    assert row["status"] == "failed"
    assert row["model_rounds"] == 1
    assert (row["input_tokens"], row["output_tokens"]) == (100, 10)
    assert [(span["name"], span["success"]) for span in provider_spans] == [
        ("response", 1), ("verification", 0),
    ]
    assert json.loads(provider_spans[1]["metadata_json"])["usage_available"] is False
    assert row["cost_usd"] == calcular_custo_estimado(
        {"input_tokens": 100, "output_tokens": 10}, "gpt-5.6-luna",
    )
    assert row["cost_status"] == "partial"


def test_observer_is_scoped_to_the_active_task(tmp_path):
    provider, _ = _provider(_response(text="ok", usage=_usage(11, 2)))
    store = TaskTraceStore(tmp_path / "scoped.sqlite3")
    harness = _harness(store, lambda entrada, *_: provider.create_response(entrada, tools=[]))

    harness.processar_mensagem("explique este conceito")
    task_id = harness.current_task().task_id
    original_spans = store.get_spans(task_id)

    other_provider, _ = _provider(_response(text="fora da tarefa", usage=_usage(3, 1)))
    other_provider.create_response("consulta direta", tools=[])
    assert store.get_spans(task_id) == original_spans


def test_telemetry_failure_does_not_change_provider_result():
    provider, sdk_calls = _provider(_response(text="ok", usage=_usage(1, 1)))

    def broken_observer(*_args):
        raise RuntimeError("trace offline")

    token = usage.set_model_call_observer(broken_observer)
    try:
        response = provider.create_response("pedido", tools=[])
    finally:
        usage.reset_model_call_observer(token)

    assert response.output_text == "ok"
    assert len(sdk_calls) == 1
