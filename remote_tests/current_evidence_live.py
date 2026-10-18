"""One new Live scenario, using only the 3 remaining authorized requests."""
import argparse
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from remote_tests.live_budget import LiveBudget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--budget-ledger', required=True)
    args = parser.parse_args()
    if (os.getenv('AUREN_NOTIFICATION_LIVE_AUTHORIZED') != '1'
            or not os.getenv('OPENAI_API_KEY') or os.getenv('AUREN_TEST_MODE') != '1'):
        raise RuntimeError('Explicit authorization and in-memory credential required')
    output = Path(args.artifacts).resolve()
    output.mkdir(parents=True, exist_ok=False)
    assert Path(os.environ['USERPROFILE']).resolve().is_relative_to(output.parent)
    assert not (Path(__file__).resolve().parents[1]/'.env').exists()
    # No reset: append to the same ledger used by PR #163.
    budget = LiveBudget(args.budget_ledger, resume=True)
    initial_calls = len(budget.data['calls'])
    assert initial_calls == 5 and budget.MAX_CALLS == 8 and budget.MAX_USD == .5
    from openai import OpenAI
    from core import response
    from core.permission_manager import PermissionLevel
    from core.routines import RoutineScheduler
    from core.task_manager import TaskManager, TaskState
    sdk = OpenAI(max_retries=0, timeout=30)
    response._orchestrator.provider._client = SimpleNamespace(responses=SimpleNamespace(
        create=lambda **kwargs:budget.create(sdk.responses.create, **kwargs)))
    import auren
    assert auren.MODEL == budget.MODEL
    h = auren.criar_harness(confirmation_channel=SimpleNamespace(confirmar=lambda _:False),
        task_db_path=output/'tasks.sqlite3')
    for capability in h.permission_manager.policy:
        if capability not in {'file.read','file.inspect'}:
            h.permission_manager.policy[capability] = PermissionLevel.BLOCKED
    file = Path(os.environ['USERPROFILE'])/'Documents'/'x.txt'
    relative = os.path.relpath(file, Path.cwd()).replace('\\','/')
    args_read = {'caminho':relative,'inicio':0,'limite_caracteres':200}
    goal = f'Leia "{relative}" com inicio=0 e limite_caracteres=200.'
    old_text, fresh_text = 'CODIGO_ANTIGO: 19 itens.', 'CODIGO_NOVO_K84: 23 itens.'
    result = {'initial_api_calls':initial_calls,'cases':[],'model':budget.MODEL}
    chat = h._garantir_sessao_chat()
    try:
        # Seed previous context using a real, permitted read of a synthetic file,
        # without spending a model call or inventing a successful tool result.
        file.write_text(old_text, encoding='utf-8')
        old = h.task_manager.create(goal, chat_id=chat)
        h.task_manager.start()
        h.permission_manager.iniciar_tarefa()
        h.task_manager.begin_step('ler_arquivo', json.dumps(args_read))
        observed = h.executar_ferramenta(SimpleNamespace(name='ler_arquivo', arguments=json.dumps(args_read)))
        assert observed.ok and old_text in str(observed)
        h.task_manager.finish_step(success=True, result=str(observed))
        h.task_manager.complete(old_text)
        h.context.record_turn(chat,'user',goal)
        h.context.record_turn(chat,'assistant',old_text)
        file.write_text(fresh_text, encoding='utf-8')
        service = RoutineScheduler(h.task_manager)
        now = int(time.time())
        routine = service.register(chat_id=chat, objective=goal, due_at=now, expires_at=now+600,
            mode='execute', allowed_calls=[{'name':'ler_arquivo','arguments':args_read}], model_budget=2)
        service.authorize(routine['id'], chat_id=chat)
        events = service.tick(h, chat_id=chat)
        task = h.current_task()
        passed = (task.task_id != old.task_id and task.state is TaskState.COMPLETED
            and len(task.steps)==1 and task.steps[0].success is True
            and fresh_text in task.steps[0].result and fresh_text in task.result
            and old_text not in task.result and events[0]['kind']=='completed')
        result['cases'].append({'name':'new_routine_read_with_stale_context', 'passed':passed,
            'objective':goal,'old_task_id':old.task_id,'new_task_id':task.task_id,
            'state':task.state.value,'answer':task.result,
            'steps':[{'tool':s.tool,'success':s.success,'result':s.result} for s in task.steps],
            'model_calls':task.model_calls,'model_limit':task.model_limit,'events':events})
        print(json.dumps({'case':'new_routine_read_with_stale_context','passed':passed,
            'api_calls_total':len(budget.data['calls'])}), flush=True)
        if len(budget.data['calls']) < budget.MAX_CALLS:
            _, answer = h.processar_mensagem(
                'Resuma o conteúdo que você acabou de ler, sem acessar o arquivo novamente.',
                execution_scope=lambda _:False, model_budget=1)
            t = h.current_task()
            result['cases'].append({'name':'retrospective_conversation_without_new_read',
                'passed':t.state is TaskState.COMPLETED and not t.steps
                    and '23' in answer.output_text and '19' not in answer.output_text,
                'state':t.state.value,'answer':answer.output_text,'steps':len(t.steps)})
        else:
            result['cases'].append({'name':'retrospective_conversation_without_new_read',
                'passed':False,'not_run':'No authorized requests remain'})
        assert file.read_text(encoding='utf-8') == fresh_text
        count = len(budget.data['calls'])
        assert service.tick(h, chat_id=chat) == []
        service.pending_notifications(chat_id=chat)
        assert len(budget.data['calls']) == count
        saved = {t.task_id:t.state.value for t in h.task_manager.list_snapshots(chat)}
    finally:
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        h.shutdown()
        sdk.close()
    manager = TaskManager(db_path=output/'tasks.sqlite3')
    try:
        assert all(manager.get_snapshot(k).state.value==v for k,v in saved.items())
    finally:
        manager.close()
    result.update(passed=sum(c['passed'] for c in result['cases']),
        failed=sum(not c['passed'] for c in result['cases']),
        new_api_calls=len(budget.data['calls'])-initial_calls, total_api_calls=len(budget.data['calls']),
        estimated_usd_total=budget.data['estimated_usd'], reserved_upper_usd_total=budget.data['reserved_upper_usd'],
        billing_confirmed=False,persistent_states_reopened=saved,personal_effects=0)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
