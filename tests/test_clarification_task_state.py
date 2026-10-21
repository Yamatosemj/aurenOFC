"""Clarification lifecycle with deterministic providers and disposable managers."""
import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from core.tool_result import ToolResult
from tools import dispatcher


def response(text='', calls=()):
    return SimpleNamespace(output_text=text,output=list(calls),usage=None)


def call(name='definir_volume_windows', **args):
    return SimpleNamespace(type='function_call',name=name,arguments=json.dumps(args or (
        {'percentual':30} if name=='definir_volume_windows' else {})),call_id='fixture')


@pytest.fixture(params=[False,True],ids=['memory','sqlite'])
def build(request,tmp_path,monkeypatch):
    opened=[]
    def make(answers,decisions=(),approved=True):
        answers=iter(answers);decisions=iter(decisions)
        seen=[];effects=[];confirmations=[]
        pm=PermissionManager(confirmation_channel=SimpleNamespace(
            confirmar=lambda req:confirmations.append(req) or approved))
        manager=TaskManager(**({'db_path':tmp_path/(str(len(opened))+'.sqlite3')} if request.param else {}))
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS,'definir_volume_windows',
            lambda *a:effects.append('volume') or ToolResult.success('volume ajustado'))
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS,'obter_status_windows',
            lambda *a:effects.append('read') or ToolResult.success('status fixture'))
        def model(entrada,*a,**kw):
            seen.append(str(entrada))
            value=next(answers)
            if isinstance(value,Exception):raise value
            return value
        h=AurenHarness(task_manager=manager,permission_manager=pm,
            criar_resposta=model,obter_chamadas=lambda r:r.output,
            executar_ferramenta=lambda item:dispatcher.executar_ferramenta(item,pm,None),
            mostrar_uso=lambda:None,comando_rapido=lambda m:(False,''),
            iniciar_tarefa=pm.iniciar_tarefa,apos_tarefa=None,fechar=lambda:None,
            verificar_conclusao=lambda snap:{'summary':'fixture','answer_status':'verified',
                'steps':[{'index':s.index,'status':'verified','evidence':list(range(1,len(snap.steps)+1))}
                    for s in snap.plan.steps]},
            verificar_intencao=lambda *a:next(decisions))
        opened.append(h)
        return h,seen,effects,confirmations
    yield make
    for h in opened:h.shutdown()


ASK=IntentDecision('esclarecer','preferencia ausente','Qual volume voce deseja?')
ALLOW=IntentDecision('aprovar','fixture')
GOAL='Ajuste a configuracao de audio conforme minha preferencia.'


def wait_for_answer(h):
    _,answer=h.processar_mensagem(GOAL)
    snap=h.current_task()
    assert answer.output_text==ASK.pergunta
    assert snap.state is TaskState.WAITING
    assert not snap.finished_at and snap.result=='' and snap.steps==()
    return snap


def test_clarification_keeps_original_task_pending(build):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    wait_for_answer(h)
    assert effects==[] and h._pergunta_pendente is not None


def test_answer_completes_same_task_and_does_not_repeat_effect(build):
    h,seen,effects,confirmations=build([response(calls=[call()]),
        response(calls=[call(),call('obter_status_windows')]),response('Feito.')],[ASK,ALLOW])
    pending=wait_for_answer(h)
    h.processar_mensagem('30 por cento')
    final=h.current_task()
    assert final.task_id==pending.task_id and final.objective==GOAL
    assert final.state is TaskState.COMPLETED and len(final.steps)==2,final.error
    assert effects==['volume','read'] and len(confirmations)==1
    assert '30 por cento' in seen[1] and h._pergunta_pendente is None
    assert h.trace_store.get_task(final.task_id)['status']=='completed'


@pytest.mark.parametrize('answer',['nao','cancelar'])
def test_user_cancels_waiting_original_task(build,answer):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    snap=wait_for_answer(h)
    h.processar_mensagem(answer)
    assert h.current_task().task_id==snap.task_id
    assert h.current_task().state is TaskState.CANCELLED
    assert effects==[] and len(seen)==1 and h._pergunta_pendente is None


def test_cancel_button_ends_idle_wait_instead_of_leaving_cancel_requested(build):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    wait_for_answer(h)
    assert h.cancel_current_task()
    assert h.current_task().state is TaskState.CANCELLED
    assert h._pergunta_pendente is None and effects==[]


def test_failure_in_continuation_belongs_to_original_task(build):
    h,seen,effects,_=build([response(calls=[call()]),TimeoutError('fixture failure')],[ASK])
    snap=wait_for_answer(h)
    h.processar_mensagem('30 por cento')
    assert h.current_task().task_id==snap.task_id
    assert h.current_task().state is TaskState.FAILED
    assert effects==[] and h._pergunta_pendente is None


@pytest.mark.parametrize('answer',['','nao sei','talvez','ola','O que significa isso?','sim'])
def test_irrelevant_or_ambiguous_answer_keeps_wait_without_effect(build,answer):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    snap=wait_for_answer(h)
    _,answer=h.processar_mensagem(answer)
    assert h.current_task().task_id==snap.task_id
    assert h.current_task().state is TaskState.WAITING
    assert answer.output_text==ASK.pergunta and effects==[] and len(seen)==1


@pytest.mark.parametrize('goal,answer',[('ola','Ola! Como posso ajudar?'),
    ('Quanto e dois mais dois?','Quatro.'),('obrigado','De nada! Precisa de mais alguma coisa?'),
    ('Explique gravidade','Ela atrai massas. Entendeu?')])
def test_ordinary_conversation_does_not_wait(build,goal,answer):
    h,seen,effects,_=build([response(answer)])
    h.processar_mensagem(goal)
    assert h.current_task().state is TaskState.COMPLETED and h._pergunta_pendente is None


def test_expired_original_scope_is_not_reauthorized_by_answer(build):
    h,seen,effects,_=build([response(calls=[call()]),response(calls=[call()])],[ASK,ALLOW])
    active=[True]
    h.processar_mensagem(GOAL,execution_scope=lambda _:active[0])
    snap=h.current_task()
    assert snap.state is TaskState.WAITING
    active[0]=False
    h.processar_mensagem('30 por cento')
    assert h.current_task().task_id==snap.task_id and h.current_task().state is TaskState.FAILED
    assert effects==[]


def test_permission_denial_still_blocks_continuation(build):
    h,seen,effects,confirmations=build([response(calls=[call()]),response(calls=[call()]),response('Nao executei.')],
        [ASK,ALLOW],approved=False)
    snap=wait_for_answer(h)
    h.processar_mensagem('30 por cento')
    assert h.current_task().task_id==snap.task_id and h.current_task().state is TaskState.FAILED
    assert effects==[] and len(confirmations)==1


def test_clarification_after_read_preserves_read_step(build):
    h,seen,effects,_=build([response(calls=[call('obter_status_windows')]),
        response(calls=[call()]),response(calls=[call(),call('obter_status_windows')]),response('Feito.')],[ASK,ALLOW])
    h.processar_mensagem('Consulte o status e depois ajuste conforme minha preferencia.')
    pending=h.current_task()
    assert pending.state is TaskState.WAITING and len(pending.steps)==1
    h.processar_mensagem('30 por cento')
    assert h.current_task().task_id==pending.task_id
    assert effects==['read','volume','read'] and len(h.current_task().steps)==3


def test_directed_text_question_is_pending_not_a_success(build):
    h,seen,effects,_=build([response('Qual cor voce prefere?'),response('Azul selecionado.')])
    h.processar_mensagem('Escolha uma cor de acordo com minha preferencia.')
    pending=h.current_task()
    assert pending.state is TaskState.WAITING
    h.processar_mensagem('azul')
    assert h.current_task().task_id==pending.task_id and h.current_task().state is TaskState.COMPLETED


def test_shutdown_cancels_waiting_task_and_clears_session(build):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    snap=wait_for_answer(h)
    h.shutdown()
    assert h.task_manager.get_snapshot(snap.task_id).state is TaskState.CANCELLED
    assert h._pergunta_pendente is None


def test_explicit_new_request_cancels_pending_and_has_separate_identity(build):
    h,seen,effects,_=build([response(calls=[call()]),response(calls=[call('obter_status_windows')]),response('Status consultado.')],[ASK])
    snap=wait_for_answer(h)
    h.processar_mensagem('Consulte o status do Windows.')
    assert h.task_manager.get_snapshot(snap.task_id).state is TaskState.CANCELLED
    assert h.current_task().task_id!=snap.task_id and effects==['read']
    assert h._pergunta_pendente is None


def test_completed_effect_is_not_replayed_on_continuation(build):
    h,seen,effects,_=build([response(calls=[call(percentual=30)]),
        response(calls=[call(percentual=40)]),response(calls=[call(percentual=30)])],[ALLOW,ASK])
    h.processar_mensagem('Defina um volume e depois altere outro volume conforme minha preferencia.')
    snap=h.current_task()
    assert snap.state is TaskState.WAITING and effects==['volume']
    h.processar_mensagem('40 por cento')
    assert h.current_task().task_id==snap.task_id and h.current_task().state is TaskState.FAILED
    assert h.current_task().error=='clarification_effect_repeated' and effects==['volume']


def test_continuation_preserves_action_budget(build):
    h,seen,effects,_=build([response(calls=[call(percentual=30)]),
        response(calls=[call(percentual=40)]),response(calls=[call(percentual=40)]),response('Nao executei.')],[ALLOW,ASK,ALLOW])
    h.permission_manager.max_actions=1
    h.processar_mensagem('Defina um volume e depois altere outro volume conforme minha preferencia.')
    assert h.current_task().state is TaskState.WAITING
    h.processar_mensagem('40 por cento')
    assert h.current_task().state is TaskState.FAILED and effects==['volume']
    assert h.permission_manager.max_actions==1


def test_session_end_does_not_carry_question_to_new_chat(build):
    h,seen,effects,_=build([response(calls=[call()])],[ASK])
    snap=wait_for_answer(h)
    h._encerrar_sessao_chat('closed')
    assert h.task_manager.get_snapshot(snap.task_id).state is TaskState.CANCELLED
    h.processar_mensagem('sim')
    assert h.current_task().task_id!=snap.task_id and h.current_task().state is TaskState.COMPLETED
    assert effects==[] and len(seen)==1


def test_text_clarification_after_effect_preserves_progress(build):
    h,seen,effects,confirmations=build([response(calls=[call(percentual=30)]),
        response('Qual volume voce deseja agora?'),
        response(calls=[call(percentual=40),call('obter_status_windows')]),response('Feito.')],[ALLOW,ALLOW])
    h.processar_mensagem('Defina um volume e depois altere outro volume conforme minha preferencia.')
    snap=h.current_task()
    assert snap.state is TaskState.WAITING and effects==['volume']
    h.processar_mensagem('40 por cento')
    assert h.current_task().task_id==snap.task_id and h.current_task().state is TaskState.COMPLETED
    # First volume action is AUTO under existing policy; restored continuation
    # restrictions require a fresh confirmation for the next effect.
    assert effects==['volume','volume','read'] and len(confirmations)==1


def test_explicit_reviewer_prompt_without_question_mark_still_waits(build):
    prompt='Informe o volume desejado'
    h,seen,effects,_=build([response(calls=[call()])],[IntentDecision('esclarecer','fixture',prompt)])
    _,answer=h.processar_mensagem(GOAL)
    assert answer.output_text==prompt and h.current_task().state is TaskState.WAITING
    assert h._pergunta_pendente is not None and effects==[]
