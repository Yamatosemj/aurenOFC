"""Reproducible recovery cases; real Harness, no paid model or desktop."""
from types import SimpleNamespace
import sys
import pytest
from core.execution_progress import observer
from core.permission_manager import PermissionManager
from core.task_manager import TaskState
from core.task_trace import TaskTraceStore
from core.tool_result import ToolResult
from tests.test_harness_loop_owner import _Bench, _resp, _call
from tools import dispatcher


@pytest.mark.parametrize('code', ['permission_denied', 'unknown_tool', 'not_implemented',
    'application_not_found', 'application_search_timeout', 'application_launch_failed', 'application_access_denied'])
def test_terminal_failure_stops_without_extra_model_or_effect(tmp_path, code):
    bench = _Bench(lambda n, b: _resp([_call(n)]),
        lambda _: ToolResult.failure('fixture', error_code=code))
    bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
    try:
        _, answer, snapshot = bench.run('leia a pagina atual')
        assert snapshot.state is TaskState.FAILED
        assert code in snapshot.error
        assert bench.model_calls == 1 and len(bench.tools) == 1
        assert 'etapas anteriores' in answer.output_text.lower()
    finally:
        bench.harness.shutdown()


def test_generic_failure_retries_at_most_twice_without_progress(tmp_path):
    bench = _Bench(lambda n, b: _resp([_call(n)]),
        lambda _: ToolResult.failure('fixture', error_code='transient_fixture'))
    bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
    try:
        _, _, task = bench.run('leia a pagina atual')
        assert task.state is TaskState.FAILED and 'tool_no_progress' in task.error
        assert len(bench.tools) == 2 and bench.model_calls == 3
    finally:
        bench.harness.shutdown()


def test_terminal_failure_stops_remaining_batch(tmp_path):
    bench = _Bench(lambda n, b: _resp([_call(1), _call(2, 'abrir_programa')]),
        lambda _: ToolResult.failure('negado', error_code='permission_denied'))
    bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
    try:
        _, _, task = bench.run('leia a pagina e abra um programa')
        assert task.state is TaskState.FAILED
        assert bench.tools == ['ler_pagina']
    finally:
        bench.harness.shutdown()


@pytest.mark.parametrize('status', ['incomplete', 'failed', 'cancelled', 'in_progress', 'queued'])
def test_incomplete_model_cannot_execute_partial_tools(tmp_path, status):
    value = _resp([_call(1, 'abrir_programa')], text='Tudo concluído')
    value.status = status
    bench = _Bench(lambda n, b: value)
    bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
    try:
        _, answer, task = bench.run('abra um programa')
        assert task.state is TaskState.FAILED and bench.tools == []
        assert 'incompleta' in answer.output_text
        bench._model = lambda n, b: _resp(text='Conversa seguinte saudável')
        assert bench.run('oi')[2].state is TaskState.COMPLETED
    finally:
        bench.harness.shutdown()


def test_sdk_attempts_are_bounded_without_constructing_real_client(monkeypatch):
    from providers.openai_provider import OpenAIProvider
    captured = []
    monkeypatch.delenv('AUREN_TEST_MODE', raising=False)
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=lambda **kw: captured.append(kw) or object()))
    provider = OpenAIProvider()
    assert provider.get_client() is provider.get_client()
    assert captured == [{'timeout': 45.0, 'max_retries': 0}]


def test_progress_tracks_actual_execution_and_denied_tool_never_emits_tool(tmp_path, monkeypatch):
    labels = []
    token = observer.set(labels.append)
    manager = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: False))
    try:
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'obter_status_windows', lambda *args: ToolResult.success('fixture'))
        bench = _Bench(lambda n, b: _resp([_call(1, 'obter_status_windows')]) if n == 1 else _resp(text='fixture'),
            lambda call: dispatcher.executar_ferramenta(call, manager, None))
        bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
        bench.run('qual o status atual do Windows?')
        assert labels[:3] == ['Preparando o contexto da conversa…', 'Consultando a IA…', 'Executando a ferramenta autorizada…']
        bench.harness.shutdown()
        labels.clear()
        call = SimpleNamespace(name='encerrar_processo_windows', arguments='{"nome":"fixture.exe","pid":null,"forcar":false}')
        result = dispatcher.executar_ferramenta(call, manager, None)
        assert not result.ok and labels == []
    finally:
        observer.reset(token)


def test_failing_progress_observer_does_not_change_task(tmp_path):
    def broken(_):
        raise RuntimeError('presentation fixture')
    token = observer.set(broken)
    bench = _Bench(lambda n, b: _resp(text='Resposta do modelo simulado'))
    bench.harness.trace_store = TaskTraceStore(tmp_path/'trace.sqlite3')
    try:
        assert bench.run('oi')[2].state is TaskState.COMPLETED
    finally:
        bench.harness.shutdown()
        observer.reset(token)


@pytest.mark.parametrize('review', ['intent', 'completion'])
def test_incomplete_reviewer_cannot_approve_even_with_parseable_json(monkeypatch, review):
    from providers.openai_provider import OpenAIProvider
    from core.intent_verification import IntentVerificationFailure
    import core.task_verification as completion
    monkeypatch.setattr(completion, 'completion_input', lambda _: '{}')
    provider = OpenAIProvider()
    partial = SimpleNamespace(status='incomplete', output_text='{"answer_status":"verified"}', usage=None)
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: partial))
    with pytest.raises((IntentVerificationFailure, RuntimeError)):
        if review == 'intent':
            provider.verify_intent('fixture', [_call(1, 'abrir_programa')], [])
        else:
            provider.verify_completion(None)
