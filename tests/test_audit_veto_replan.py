from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.task_manager import TaskState
from core.tool_result import ToolResult


def run_case(second_value, decisions, max_rounds=4):
    calls, reviews, requests = [], [], []
    def response(value=None):
        output = [] if value is None else [SimpleNamespace(type='function_call',
            name='definir_volume_windows', arguments='{"percentual":' + str(value) + '}', call_id=str(value))]
        return SimpleNamespace(output=output, output_text='Ajuste concluído.' if value is None else '', usage=None)
    responses = [response(30), response(second_value), response()]
    def model(*args):
        requests.append(args)
        return responses.pop(0)
    def review(*args):
        reviews.append(args)
        return IntentDecision(decisions[min(len(reviews) - 1, len(decisions) - 1)], 'valor incompatível')
    harness = AurenHarness(criar_resposta=model,
        executar_ferramenta=lambda item: calls.append(item.arguments) or ToolResult.success('Volume definido.'),
        mostrar_uso=lambda: None, obter_chamadas=lambda response: response.output,
        comando_rapido=lambda message: (False, ''), iniciar_tarefa=lambda: None,
        apos_tarefa=None, fechar=lambda: None, verificar_intencao=review, max_model_rounds=max_rounds)
    try:
        harness.processar_mensagem('ajuste o áudio conforme o pedido detalhado')
        return calls, reviews, requests, harness.current_task().state
    finally:
        harness.shutdown()


def test_liv006_one_different_proposal_is_reviewed_before_execution():
    calls, reviews, requests, state = run_case(20, ['bloquear', 'aprovar'])
    assert calls == ['{"percentual":20}']
    assert len(reviews) == 2 and len(requests) <= 3
    assert state is TaskState.COMPLETED


@pytest.mark.parametrize('second,decisions', [(30, ['bloquear', 'aprovar']),
    (20, ['bloquear', 'bloquear']), (None, ['bloquear'])])
def test_liv006_same_proposal_second_veto_or_empty_replan_stops(second, decisions):
    calls, reviews, requests, state = run_case(second, decisions)
    assert calls == [] and len(requests) == 2
    assert state is TaskState.FAILED


def test_liv006_replan_never_exceeds_round_budget():
    calls, reviews, requests, state = run_case(20, ['bloquear', 'aprovar'], max_rounds=1)
    assert calls == [] and len(requests) == 1
    assert state is TaskState.FAILED
