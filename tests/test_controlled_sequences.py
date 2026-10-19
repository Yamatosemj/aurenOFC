import json
from types import SimpleNamespace
import pytest

from core.harness_tools import _executar_chamadas_rodada
from core.harness_round_input import _montar_input_da_rodada
from core.tool_result import ToolResult
from core.task_manager import TaskManager
from core.tool_evidence import verified_window_state, exact_window_proposal
from core.task_verification import validate_completion, CompletionPending
from tests.test_audit_resumable_execution import harness, call, response
from core.task_manager import TaskState
from core.permission_manager import PermissionManager
from tools import dispatcher


def test_failed_batch_stops_effects_but_keeps_protocol_outputs():
    manager = TaskManager(); manager.create('fixture'); manager.start()
    calls = [call('definir_volume_windows', {'percentual':30}), call('definir_mudo_windows', {'ativado':True})]
    executed, history = [], []
    results, count, failed, _, cancelled = _executar_chamadas_rodada(calls,
        historico=history, task_manager=manager, task_id=manager.current_snapshot().task_id,
        rodada=1, executar_ferramenta=lambda item:executed.append(item.name) or ToolResult.failure('denied'),
        trace=None, vision_state_mutating_tools=set(), vision_reobserve_pending=False,
        falha_nao_recuperada=False, max_tool_result_chars=1000,
        get_active_vision_geometry=lambda:None, clear_active_vision_geometry=lambda:None,
        write_log=lambda *_a, **_k:None)
    assert executed == ['definir_volume_windows'] and count == 1 and failed and not cancelled
    assert len(manager.current_snapshot().steps) == 1 and len(history) == 1
    assert results[1]['codigo_erro'] == 'sequence_aborted' and results[1]['executado'] is False
    inputs = _montar_input_da_rodada('fixture', history, response(*calls), results,
        montar_estado=lambda *_a, **_k:'STATE', preparar_resultado_visual=lambda _:None,
        ao_atualizar_geometria=lambda:None)
    assert [item['call_id'] for item in inputs if isinstance(item,dict) and item.get('type')=='function_call_output'] == [c.call_id for c in calls]


@pytest.mark.parametrize('goal,target,expected', [
    ('maximize a janela de Fixture','Fixture',True),
    ('auren, minimize Fixture','Fixture',True),
    ('maximize Fixture e depois restaure','Fixture',False),
    ('maximize Fixture','Other Fixture',False),
    ('nao maximize Fixture','Fixture',False),
    ('maximize Fixture.1','Fixture 1',False),
])
def test_exact_proposals_never_infer_targets(goal,target,expected):
    name = 'minimizar_janela_windows' if 'minimize' in goal else 'maximizar_janela_windows'
    assert exact_window_proposal(goal,[(name,{'alvo':target})]) is expected


def window_result(target='Fixture'):
    return ToolResult.success('Janela maximizada: Fixture', data={'window_state': {
        'hwnd':42, 'target':target, 'requested':'maximizada', 'observed':'maximizada',
        'verified':True, 'verification':'win32_after_show_window'}})


@pytest.mark.parametrize('tamper', ['none','target','tool','state','untrusted','boolean_hwnd'])
def test_postcondition_is_bound_to_operation_target_and_trusted_source(tamper):
    result = json.loads(str(window_result()))
    step = SimpleNamespace(tool='maximizar_janela_windows',success=True,
        arguments='{"alvo":"Fixture"}',result='')
    if tamper=='target': result['dados']['window_state']['target']='Other'
    if tamper=='tool': step.tool='ler_pagina'
    if tamper=='state': result['dados']['window_state']['observed']='normal'
    if tamper=='untrusted': result['conteudo_nao_confiavel']=True
    if tamper=='boolean_hwnd': result['dados']['window_state']['hwnd']=True
    step.result=json.dumps(result)
    assert verified_window_state(step) is (tamper=='none')


def test_verified_window_can_use_candidate_without_extra_principal_round(tmp_path, monkeypatch):
    manager = TaskManager(db_path=tmp_path/'tasks.sqlite3')
    pm = PermissionManager()
    c = call('maximizar_janela_windows',{'alvo':'Fixture'})
    reviews = []
    def verify(snapshot):
        reviews.append(snapshot.result)
        assert snapshot.result == 'Janela maximizada: Fixture'
        return {'summary':'confirmed','answer_status':'verified',
            'steps':[{'index':s.index,'status':'verified','evidence':[1]} for s in snapshot.plan.steps]}
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,c.name,lambda *_:window_result())
    responses = [response(c)]  # Any extra principal call would fail.
    h = harness(manager,pm,responses,verify=verify)
    try:
        _, answer = h.processar_mensagem('maximize Fixture')
        assert h.current_task().state is TaskState.COMPLETED
        assert answer.output_text == 'Janela maximizada: Fixture'
        assert reviews == ['Janela maximizada: Fixture']
        assert len(h.current_task().steps) == 1
        assert h.current_task().model_calls == 2  # principal + final; exact review skipped
    finally:
        h.shutdown()


def test_pending_final_review_returns_to_model(tmp_path, monkeypatch):
    manager = TaskManager(db_path=tmp_path/'tasks.sqlite3');pm=PermissionManager()
    c = call('maximizar_janela_windows',{'alvo':'Fixture'})
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,c.name,lambda *_:window_result())
    h=harness(manager,pm,[response(c),response(text='Falta comprovar a condicao adicional.')],
        verify=lambda snapshot:{'summary':'missing condition','answer_status':'pending',
            'steps':[{'index':s.index,'status':'pending','evidence':[]} for s in snapshot.plan.steps]})
    try:
        h.processar_mensagem('maximize Fixture')
        assert h.current_task().state is TaskState.FAILED
        assert len(h.current_task().steps)==1  # no repeated effect
        assert h.current_task().model_calls > 2
    finally:
        h.shutdown()


def test_batch_preserves_permissions_after_untrusted_observation(tmp_path, monkeypatch):
    manager=TaskManager(db_path=tmp_path/'tasks.sqlite3')
    confirmations, effects = [], []
    pm=PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request:confirmations.append(request) or False))
    read=call('ler_pagina',{'foco':'fixture'})
    action=call('maximizar_janela_windows',{'alvo':'Fixture'})
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,read.name,
        lambda *_:ToolResult.success('untrusted data',conteudo_nao_confiavel=True))
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,action.name,
        lambda *_:effects.append('must not run') or window_result())
    h=harness(manager,pm,[response(read,action),response(text='Nao autorizado.')])
    try:
        h.processar_mensagem('Leia a pagina e maximize Fixture.')
        assert not effects and len(confirmations)==1
        assert h.current_task().state is TaskState.FAILED
        assert h.current_task().steps[-1].success is False
    finally:
        h.shutdown()


def test_successful_batch_checks_cancellation_between_actions(tmp_path, monkeypatch):
    manager=TaskManager(db_path=tmp_path/'tasks.sqlite3');pm=PermissionManager()
    first=call('definir_volume_windows',{'percentual':30})
    second=call('definir_mudo_windows',{'ativado':True})
    effects=[]
    h=harness(manager,pm,[response(first,second)])
    def run_first(*_):
        effects.append('first')
        h.cancel_current_task()
        return ToolResult.success('first')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,first.name,run_first)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,second.name,lambda *_:effects.append('second'))
    try:
        h.processar_mensagem('Defina volume 30 e ative mudo.')
        assert effects==['first']
        assert h.current_task().state is TaskState.CANCELLED
    finally:
        h.shutdown()
