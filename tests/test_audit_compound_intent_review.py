"""Contratos do pedido composto; modelo e efeitos do Windows sao simulados.

A regressao da decisao do modelo real e documentada no relatorio Live.
Estes testes verificam continuidade, revisao de cada passo e permissoes.
"""
import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskState
from core.tool_result import ToolResult
from tools import dispatcher


OBJECTIVE = (
    'Mova a janela Relatorio Ficticio para x=120 e y=140 e redimensione '
    'essa mesma janela para largura=800 e altura=500.'
)


@pytest.mark.parametrize('second_review', ['aprovar', 'esclarecer', 'bloquear', 'indisponivel'])
def test_each_compound_step_is_reviewed_before_dispatch(monkeypatch, second_review):
    events = []
    reviews = []
    move = SimpleNamespace(type='function_call', name='mover_janela_windows',
        arguments=json.dumps({'alvo': 'Relatorio Ficticio', 'x': 120, 'y': 140}), call_id='move')
    resize = SimpleNamespace(type='function_call', name='redimensionar_janela_windows',
        arguments=json.dumps({'alvo': 'Relatorio Ficticio', 'largura': 800, 'altura': 500}), call_id='resize')
    responses = [SimpleNamespace(output=[move], output_text='', usage=None),
        SimpleNamespace(output=[resize], output_text='', usage=None),
        SimpleNamespace(output=[resize] if second_review == 'bloquear' else [],
            output_text='As duas alteracoes foram realizadas.', usage=None)]

    def review(objective, calls, history):
        assert objective == OBJECTIVE
        name = calls[0].name
        events.append(('review', name))
        reviews.append((name, list(history)))
        if len(reviews) == 1:
            assert not history
            return IntentDecision('aprovar', 'Movimento explicitamente solicitado.')
        assert history[-1]['ferramenta'] == move.name
        if second_review == 'indisponivel':
            raise TimeoutError('Revisor ficticio indisponivel')
        return IntentDecision(second_review, 'Decisao ficticia do segundo passo.',
            'Qual janela voce deseja alterar?' if second_review == 'esclarecer' else '')

    def handler(name):
        def execute(args, store, context):
            events.append(('execute', name))
            return ToolResult.success('Etapa ficticia executada.')
        return execute

    for item in (move, resize):
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name, handler(item.name))
    manager = PermissionManager()
    harness = AurenHarness(criar_resposta=lambda *_: responses.pop(0),
        executar_ferramenta=lambda item: dispatcher.executar_ferramenta(item, manager, None),
        mostrar_uso=lambda: None, obter_chamadas=lambda response: response.output,
        comando_rapido=lambda _: (False, ''), iniciar_tarefa=manager.iniciar_tarefa,
        apos_tarefa=None, fechar=lambda: None, verificar_intencao=review, max_model_rounds=3)
    try:
        _, response = harness.processar_mensagem(OBJECTIVE)
        assert len(reviews) == 2
        assert events[:3] == [('review', move.name), ('execute', move.name), ('review', resize.name)]
        if second_review == 'aprovar':
            assert events[3:] == [('execute', resize.name)]
            assert harness.current_task().state is TaskState.COMPLETED
            assert len(harness.current_task().steps) == 2
        else:
            assert len(events) == 3
            assert len(harness.current_task().steps) == 1
            if second_review == 'esclarecer':
                assert response.output_text == 'Qual janela voce deseja alterar?'
            else:
                assert harness.current_task().state is TaskState.FAILED
    finally:
        harness.shutdown()


def test_semantic_approval_does_not_approve_permission_confirmation(monkeypatch):
    confirmations, effects, reviews = [], [], []
    channel = SimpleNamespace(confirmar=lambda request: confirmations.append(request) or False)
    manager = PermissionManager(confirmation_channel=channel)
    item = SimpleNamespace(type='function_call', name='mover_janela_windows',
        arguments='{"alvo":"Relatorio Ficticio","x":120,"y":140}', call_id='move')
    responses = [SimpleNamespace(output=[item], output_text='', usage=None),
        SimpleNamespace(output=[], output_text='A confirmacao foi negada.', usage=None)]
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name,
        lambda *args: effects.append(args) or ToolResult.success('Nunca executar.'))

    def start():
        manager.iniciar_tarefa()
        manager.registrar_fonte_nao_confiavel('memoria ficticia')

    harness = AurenHarness(criar_resposta=lambda *_: responses.pop(0),
        executar_ferramenta=lambda call: dispatcher.executar_ferramenta(call, manager, None),
        mostrar_uso=lambda: None, obter_chamadas=lambda response: response.output,
        comando_rapido=lambda _: (False, ''), iniciar_tarefa=start,
        apos_tarefa=None, fechar=lambda: None,
        verificar_intencao=lambda *args: reviews.append(args) or IntentDecision('aprovar', 'Passo correto.'),
        max_model_rounds=2)
    try:
        harness.processar_mensagem(OBJECTIVE)
        assert len(reviews) == 1 and len(confirmations) == 1
        assert not effects
        assert harness.current_task().state is TaskState.FAILED
        assert harness.current_task().steps[0].success is False
    finally:
        harness.shutdown()
