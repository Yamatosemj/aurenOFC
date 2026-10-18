"""Manual opt-in Live validation; real factory/provider and fictitious data only."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from remote_tests.live_budget import LiveBudget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--budget-ledger', required=True)
    args = parser.parse_args()
    if os.getenv('AUREN_NOTIFICATION_LIVE_AUTHORIZED') != '1' or not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('Explicit cycle authorization and in-memory API credential required')
    assert os.getenv('AUREN_TEST_MODE') == '1'
    output = Path(args.artifacts).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # The external launcher has copied sources only and set a synthetic profile.
    assert Path(os.environ['USERPROFILE']).resolve().is_relative_to(output.parent)
    assert not (Path(__file__).resolve().parents[1]/'.env').exists()
    budget = LiveBudget(args.budget_ledger)
    from openai import OpenAI
    from core import response
    from core.permission_manager import PermissionLevel
    from core.routines import RoutineScheduler
    from core.task_manager import TaskManager, TaskState
    sdk = OpenAI(max_retries=0, timeout=30)
    response._orchestrator.provider._client = SimpleNamespace(responses=SimpleNamespace(
        create=lambda **kwargs: budget.create(sdk.responses.create, **kwargs)))
    import auren
    assert auren.MODEL == budget.MODEL
    documents = Path(os.environ['USERPROFILE'])/'Documents'
    file = documents/'x.txt'
    file.write_text('CODIGO_FICTICIO_Z73: 19 itens.', encoding='utf-8')
    original = file.read_bytes()
    confirmations = []
    def deny(request):
        confirmations.append(request.tool_name)
        return False
    h = auren.criar_harness(confirmation_channel=SimpleNamespace(confirmar=deny),
        task_db_path=output/'tasks.sqlite3')
    # Restrict the test environment; no Windows, browser, memory or network tools
    # can execute. Existing file permission checks still run inside Dispatcher.
    for name in h.permission_manager.policy:
        if name not in {'file.read', 'file.inspect'}:
            h.permission_manager.policy[name] = PermissionLevel.BLOCKED
    def scope(call):
        if call.name not in {'ler_arquivo', 'inspecionar_arquivo'}:
            return False
        try:
            return Path(json.loads(call.arguments)['caminho']).resolve() == file.resolve()
        except (ValueError, TypeError, KeyError, OSError):
            return False
    cases = []
    def snapshot_case(name, quick, answer, valid):
        task = h.current_task()
        case = {'name': name, 'passed': bool(valid), 'answer': str(answer if quick else answer.output_text),
            'task_id': task.task_id, 'state': task.state.value, 'objective': task.objective,
            'model_calls': task.model_calls, 'model_limit': task.model_limit,
            'steps': [{'tool':s.tool,'success':s.success,'result':s.result[:1000]} for s in task.steps],
            'api_calls_so_far': len(budget.data['calls'])}
        cases.append(case)
        (output/'result.json').write_text(json.dumps({'cases': cases}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'case':name, 'passed':case['passed'], 'calls':len(budget.data['calls'])}), flush=True)
    try:
        quick, answer = h.processar_mensagem('ola auren', execution_scope=scope, model_budget=2)
        snapshot_case('real_greeting_has_no_pending_clarification', quick, answer,
            h.current_task().state is TaskState.COMPLETED and h._pergunta_pendente is None)
        # A genuinely new command after the real greeting; evidence is a file
        # read through the real Dispatcher/PermissionManager, not model prose.
        relative_file = os.path.relpath(file, Path.cwd()).replace('\\', '/')
        goal = f'Leia "{relative_file}".'
        quick, answer = h.processar_mensagem(goal, execution_scope=scope, model_budget=3)
        task = h.current_task()
        snapshot_case('new_goal_uses_real_file_evidence_and_persists_state', quick, answer,
            task.objective == goal and task.state is TaskState.COMPLETED
            and any(s.tool == 'ler_arquivo' and s.success is True and 'CODIGO_FICTICIO_Z73' in s.result for s in task.steps)
            and 'CODIGO_FICTICIO_Z73' in str(answer if quick else answer.output_text))
        service = RoutineScheduler(h.task_manager)
        chat = h._session.chat_id
        import time
        now = int(time.time())
        routine_goal = f'Leia "{relative_file}" com inicio=0 e limite_caracteres=200.'
        routine = service.register(chat_id=chat, objective=routine_goal, due_at=now, expires_at=now+600,
            mode='execute', allowed_calls=[{'name':'ler_arquivo', 'arguments':{
                'caminho':relative_file,'inicio':0,'limite_caracteres':200}}], model_budget=2)
        # This is an explicit bounded fixture grant to read a synthetic file,
        # not an automatic answer to a PermissionManager confirmation.
        service.authorize(routine['id'], chat_id=chat)
        # The exact scope above intentionally remains strict: a model choosing
        # different arguments must fail instead of widening the permission.
        events = service.tick(h, chat_id=chat)
        pending = service.pending_notifications(chat_id=chat)
        t = h.current_task()
        cases.append({'name':'real_model_in_bounded_routine', 'passed':bool(
            events and events[0]['kind']=='completed' and pending and pending[0]['kind']=='completed'
            and any(s.success is True and 'CODIGO_FICTICIO_Z73' in s.result for s in t.steps)),
            'events':events, 'state':t.state.value, 'model_calls':t.model_calls,
            'steps':[{'tool':s.tool,'success':s.success,'result':s.result[:1000]} for s in t.steps],
            'pending_notice_count':len(pending)})
        # Do not pay to retry a failed exact routine grant.
        before = len(service.list(chat_id=chat))
        remaining = budget.MAX_CALLS-len(budget.data['calls'])
        if remaining:
            goal = 'Crie um lembrete para estudar daqui a 10 minutos sem abrir aplicativos nem navegar.'
            quick, answer = h.processar_mensagem(goal, execution_scope=scope, model_budget=min(2, remaining))
            text = str(answer if quick else answer.output_text)
            from core.utils import normalizar_nome
            normalized = normalizar_nome(text)
            unavailable = any(term in normalized for term in ('nao consigo','nao posso','nao tenho','indisponivel','nao foi','nao consegui','nao ha'))
            snapshot_case('missing_chat_reminder_is_not_claimed_as_created', quick, answer,
                unavailable and len(service.list(chat_id=chat)) == before
                and h.current_task().objective == goal and not any(s.success is True for s in h.current_task().steps))
        else:
            cases.append({'name':'missing_chat_reminder_is_not_claimed_as_created','passed':False,
                'not_run':'API call budget exhausted; no additional request made'})
        assert file.read_bytes() == original
        assert all(s.tool in {'ler_arquivo','inspecionar_arquivo'} or s.success is not True
                   for t in h.task_manager.list_snapshots(chat) for s in t.steps)
        # Re-delivery reads persisted notices only; model count must not change.
        count = len(budget.data['calls'])
        for _ in range(3):
            assert service.tick(h, chat_id=chat) == []
            service.pending_notifications(chat_id=chat)
        assert len(budget.data['calls']) == count
    finally:
        saved = {t.task_id:t.state.value for t in h.task_manager.list_snapshots(h._session.chat_id)}
        h.shutdown()
        sdk.close()
    manager = TaskManager(db_path=output/'tasks.sqlite3')
    try:
        assert all(manager.get_snapshot(k).state.value == v for k,v in saved.items())
    finally:
        manager.close()
    result = {'cases': cases, 'passed':sum(c['passed'] for c in cases),
        'failed':sum(not c['passed'] for c in cases), 'calls':len(budget.data['calls']),
        'estimated_usd':budget.data['estimated_usd'], 'reserved_upper_usd':budget.data['reserved_upper_usd'],
        'billing_confirmed':False, 'model':budget.MODEL, 'confirmation_requests_denied':confirmations,
        'persistent_states_reopened':saved, 'personal_effects':0,
        'limitation':'No chat reminder/timer tool exists; routine registered explicitly by fixture, not by chat.'}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
