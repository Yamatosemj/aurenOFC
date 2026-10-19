import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.latency import measure, observe
from core.harness import AurenHarness
from core.task_manager import TaskManager
from core.task_trace import TaskTraceStore
from core.task_verification import CompletionResult, CompletionVerificationFailure
from tools import dispatcher
from core.tool_result import ToolResult


def test_spans_are_nested_task_local_and_never_swallow_errors():
    outer, inner = [], []
    with observe(lambda *args: outer.append(args)):
        with measure('outer'):
            with observe(lambda *args: inner.append(args)):
                with pytest.raises(ValueError):
                    with measure('inner'):
                        raise ValueError('PRIVATE MESSAGE')
        with measure('restored'):
            pass
    with measure('unobserved'):
        pass
    assert [s[0] for s in outer] == ['outer', 'restored']
    assert inner[0][2:] == (False, 'ValueError')
    assert 'PRIVATE' not in repr(outer + inner)


def test_broken_observer_cannot_change_execution():
    def broken(*_):
        raise OSError('trace offline')
    with observe(broken), measure('fixture'):
        pass


def test_dispatcher_measures_permission_denial_without_executing(monkeypatch):
    spans = []
    pm = SimpleNamespace(autorizar=lambda *_: (False, 'denied'), registrar_resultado=lambda *_: None)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'maximizar_janela_windows',
                        lambda *_: pytest.fail('Unauthorized execution'))
    with observe(lambda *args: spans.append(args)):
        result = dispatcher.executar_ferramenta(SimpleNamespace(
            name='maximizar_janela_windows', arguments='{"alvo":"PRIVATE WINDOW"}'), pm, None)
    assert not result.ok and result.error_code == 'permission_denied'
    assert [s[0] for s in spans] == ['contract_validation', 'permission_validation']
    assert 'PRIVATE' not in repr(spans)


@pytest.mark.parametrize('outcome', ['verified', 'pending', 'exception'])
def test_completion_counts_usage_and_logs_only_safe_diagnostics(tmp_path, monkeypatch, outcome):
    import core.harness as module
    manager = TaskManager()
    manager.create('ola'); manager.start()
    snapshot = manager.current_snapshot()
    from agent.planner import PlanBuilder
    snapshot = replace(snapshot, plan=PlanBuilder().build('ola'))
    store = TaskTraceStore(tmp_path/'trace.sqlite3')
    trace = store.start_task(task_id='test', chat_id='chat', objective='ola')
    logs = []
    monkeypatch.setattr(module, '_write_log', lambda name, **data: logs.append((name, data)))
    usage = {'input_tokens': 123, 'output_tokens': 20}
    def verify(_):
        if outcome == 'exception':
            raise CompletionVerificationFailure('completion_response_invalid', usage)
        return CompletionResult({'summary': 'PRIVATE REVIEW', 'answer_status': outcome,
            'steps': [{'index': s.index, 'status': 'pending', 'evidence': []}
                      for s in snapshot.plan.steps]}, usage)
    if outcome == 'verified':
        monkeypatch.setattr('core.task_verification.validate_completion', lambda *_: None)
    harness = SimpleNamespace(current_task=lambda: snapshot, _requires_completion_verification=lambda: True,
        _reserve_model_call=lambda: None, verificar_conclusao=verify, _trace=trace, _task_id='test',
        _encerrar_falha=lambda *args: args)
    AurenHarness._verify_completion(harness, 'ola', candidate_answer='PRIVATE ANSWER')
    assert trace.model_rounds == 1
    assert trace.input_tokens == 123 and trace.output_tokens == 20
    event = next(data for name, data in logs if name == 'COMPLETION_VERIFICATION_RESULT')
    assert event['outcome'] == ('failed' if outcome == 'exception' else outcome)
    assert event['latencia_ms'] >= 0
    assert 'PRIVATE' not in json.dumps(logs)


def test_completion_result_keeps_original_mapping_contract():
    result = CompletionResult({'summary': 'ok', 'answer_status': 'verified', 'steps': []}, {'input_tokens': 5})
    assert isinstance(result, dict)
    assert set(result) == {'summary', 'answer_status', 'steps'}
    assert 'metricas_uso' not in json.dumps(result)
