from types import SimpleNamespace

import pytest

from core.harness_intent_guard import verificar_antes_de_agir
from providers.openai_provider import OpenAIProvider


@pytest.mark.parametrize('api_failed,usage_known', [(False, True), (True, False), (False, False)])
def test_aud020_failed_review_is_accounted_without_executing(api_failed, usage_known):
    response = SimpleNamespace(output_text='invalid fictional decision',
        usage=SimpleNamespace(input_tokens=11, output_tokens=3, input_tokens_details=None) if usage_known else None)
    def create(**kwargs):
        if api_failed:
            raise TimeoutError('fictional timeout')
        return response
    provider = OpenAIProvider()
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    traces, events, failures = [], [], []
    harness = SimpleNamespace(_task_id='fictional',
        _trace=SimpleNamespace(record_model=lambda *args: traces.append(args)),
        verificar_intencao=provider.verify_intent,
        task_manager=SimpleNamespace(should_cancel=lambda task: False),
        _encerrar_falha=lambda *args: failures.append(args) or (False, 'blocked'))
    result = verificar_antes_de_agir(harness, 'ajuste conforme o pedido detalhado',
        [SimpleNamespace(name='definir_volume_windows', arguments='{"percentual":30}')], [],
        rodada=1, resposta_wrapper=lambda text: text,
        write_log=lambda event, **data: events.append((event, data)))
    assert result == (False, 'blocked') and failures
    assert len(traces) == 1
    assert traces[0][2] == ({} if not usage_known else {
        'input_tokens': 11, 'output_tokens': 3, 'cached_tokens': 0, 'cache_write_tokens': 0})
    error = next(data for event, data in events if event == 'INTENT_VERIFICATION_ERROR')
    assert error['uso_conhecido'] is usage_known


def test_aud020_configured_model_tariff_is_used_instead_of_generic_reference(monkeypatch):
    from core import usage
    monkeypatch.setenv('AUREN_MODEL_PRICES_JSON',
        '{"fictional-model":{"input":2,"cached":1,"cache_write":3,"output":4}}')
    metrics = {'input_tokens': 1_000_000, 'output_tokens': 1_000_000,
               'cached_tokens': 0, 'cache_write_tokens': 0}
    assert usage.calcular_custo_estimado(metrics, modelo='fictional-model') == 6
    assert usage.base_do_custo('fictional-model') == 'tarifa_configurada'
    assert usage.base_do_custo('unknown-fictional') == 'referencia_generica_nao_fatura'


def test_aud020_error_usage_and_configured_tariff_reach_log_report(monkeypatch):
    from medir_metricas_router import parse_tasks
    monkeypatch.setenv('AUREN_MODEL_PRICES_JSON',
        '{"fictional-model":{"input":2,"cached":1,"cache_write":3,"output":4}}')
    prefix = '[2026-10-17T12:00:00-03:00] '
    text = prefix + 'TASK_START\n  task_id: fake\n'
    text += prefix + 'INTENT_VERIFICATION_ERROR\n  task_id: fake\n  rodada: 1\n'
    text += '  uso: {"model":"fictional-model","input_tokens":1000000,"output_tokens":1000000}\n'
    text += prefix + 'TASK_END\n  task_id: fake\n  status: failed\n'
    task = parse_tasks(text)[0]
    assert task['custo_estimado_usd'] == 6
    assert task['base_custo'] == ['tarifa_configurada']


def test_aud020_unconfigured_price_is_labeled_as_reference(monkeypatch, capsys):
    from core import usage
    monkeypatch.delenv('AUREN_MODEL_PRICES_JSON', raising=False)
    monkeypatch.setattr(usage, 'session_cost_reference_only', True)
    usage.mostrar_uso()
    assert 'referencia_generica_nao_fatura=' in capsys.readouterr().out
