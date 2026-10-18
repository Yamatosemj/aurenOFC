"""Offline cross-phase fixture using the actual UI factory and file executors."""
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import json
import os
import sys
import time


def main():
    scenario, output = sys.argv[1], Path(sys.argv[2])
    assert not os.environ.get('OPENAI_API_KEY'), 'Fixture refuses credentials'
    import auren
    from core import response
    from core.permission_manager import PermissionLevel
    from core.task_manager import TaskManager, TaskState
    from ui.backend import AurenUiWorker
    from ui.chrome_server import LocalChromeApp, ChromeServer
    checks, requests, decisions = [], [], []
    first_entered, release = Event(), Event()
    notice_ready, publish_notice = Event(), Event()
    current = {}
    documents = Path(os.environ['USERPROFILE'])/'Documents'
    files = [documents/'alfa.txt', documents/'beta.txt']
    files[0].write_text('ALFA-731: 7 itens.', encoding='utf-8')
    files[1].write_text('BETA-982: 11 itens.', encoding='utf-8')
    originals = [p.read_bytes() for p in files]
    db = output.parent/'tasks.sqlite3'

    def sdk_create(**kwargs):
        requests.append(kwargs)
        task = current['worker']._harness.current_task()
        fmt = kwargs.get('text', {}).get('format', {}).get('name')
        if fmt == 'auren_goal_completion':
            data = json.loads(kwargs['input'])
            evidence = data['execution']
            valid = (len(evidence) == 2 and all(s['success'] is True for s in evidence)
                     and 'ALFA-731' in evidence[0]['result'] and 'BETA-982' in evidence[1]['result']
                     and data['candidate_answer'] == 'ALFA-731; BETA-982; soma 18.')
            decision = {'summary': 'Comparacao ficticia com os dados realmente lidos',
                'answer_status': 'verified' if valid else 'pending',
                'steps': [{'index': s['index'], 'status': 'verified' if valid else 'pending',
                           'evidence': [1, 2] if valid else []} for s in data['plan']]}
            decisions.append(decision)
            return SimpleNamespace(output_text=json.dumps(decision), output=[], usage=None)
        assert fmt is None, 'Unexpected semantic request'
        assert any(t.get('name') == 'ler_arquivo' for t in kwargs['tools']), 'Router omitted file tool'
        if scenario == 'denial' and task.steps:
            return SimpleNamespace(output=[], output_text='A leitura foi negada; nao foi concluida.', usage=None)
        if len(task.steps) < 2:
            if scenario == 'restart' and not task.steps:
                first_entered.set()
                assert release.wait(10)
            path = files[min(len(task.steps), 1)]
            call = SimpleNamespace(type='function_call', name='ler_arquivo',
                arguments=json.dumps({'caminho': str(path), 'inicio': 0, 'limite_caracteres': 100}),
                call_id='file-'+str(len(task.steps)))
            return SimpleNamespace(output=[call], output_text='', usage=None)
        return SimpleNamespace(output=[], output_text='ALFA-731; BETA-982; soma 18.', usage=None)

    # Only the SDK transport is replaced. Factory, Router, provider request
    # building, Harness, Dispatcher, file handlers, persistence and UI are real.
    response._orchestrator.provider._client = SimpleNamespace(responses=SimpleNamespace(create=sdk_create))

    @contextmanager
    def application():
        worker = AurenUiWorker(task_db_path=db)
        current['worker'] = worker
        app = LocalChromeApp(worker)
        server = ChromeServer(app)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(path, body=None, token=True):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
            headers = {'X-Auren-Token': app.token if token else '', 'Content-Type': 'application/json'}
            try:
                connection.request('GET' if body is None else 'POST', path,
                    None if body is None else json.dumps(body), headers)
                answer = connection.getresponse()
                raw = answer.read()
                return answer.status, json.loads(raw) if path != '/' else raw.decode('utf-8')
            finally:
                connection.close()
        def snapshot():
            status, value = request('/api/events?after=0')
            assert status == 200
            return value
        def wait(predicate):
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                value = snapshot()
                if predicate(value):
                    return value
                time.sleep(.01)
            raise AssertionError('Expected UI state not observed: '+str(value))
        try:
            yield worker, request, wait, snapshot
        finally:
            release.set()
            publish_notice.set()
            server.shutdown()
            server.server_close()
            app.shutdown()
            worker._thread.join(5)
            thread.join(3)
            assert not worker.alive

    def task_control(request, value, action, *, task_id='', chat_id=''):
        return request('/api/task-action', {'action': action, 'task_id': task_id,
            'chat_id': chat_id, 'generation': value['generation']})

    if scenario == 'restart':
        objective = f'Leia o arquivo {files[0]} e depois leia o arquivo {files[1]}. Informe os codigos e a soma dos itens.'
        with application() as (worker, request, wait, snapshot):
            assert 'taskPanel' in request('/')[1]
            assert request('/api/message', {'text': objective}, token=False)[0] == 403
            assert not requests and worker._harness is None
            assert request('/api/message', {'text': objective})[0] == 200
            assert first_entered.wait(10)
            value = wait(lambda v:v['tasks'].get('tasks') and v['tasks']['tasks'][0]['state']=='waiting')
            task = value['tasks']['tasks'][0]
            task_id, chat_id = task['task_id'], value['tasks']['chat_id']
            assert task['planned_steps'] >= 2 and task['steps_done'] == 0
            assert task_control(request, value, 'pause', task_id=task_id, chat_id=chat_id)[0] == 200
            release.set()
            wait(lambda v:v['tasks']['tasks'][0]['state']=='paused' and not v['busy'])
            saved = worker._harness.current_task()
            assert len(saved.steps)==1 and saved.steps[0].success is True
            saved_calls = saved.model_calls
            checks.extend(['http_requires_token', 'real_factory_and_router', 'plan_visible', 'pause_checkpoint_saved'])
        with application() as (worker, request, wait, snapshot):
            value = snapshot()
            assert task_control(request, value, 'load')[0] == 200
            value = wait(lambda v:chat_id in v['tasks'].get('chats', []) and not v['busy'])
            assert task_control(request, value, 'select', chat_id=chat_id)[0] == 200
            # Selection publishes the new chat before its final idle event.
            # Resume must wait for both, as the real UI requires.
            value = wait(lambda v:v['tasks']['chat_id']==chat_id and not v['busy'])
            assert value['tasks']['tasks'][0]['state']=='paused'
            assert task_control(request, value, 'resume', task_id=task_id, chat_id=chat_id)[0] == 200
            wait(lambda v:v['tasks']['tasks'][0]['state']=='completed' and not v['busy'])
            task = worker._harness.current_task()
            assert task.task_id==task_id and len(task.steps)==2
            assert task.result=='ALFA-731; BETA-982; soma 18.' and len(decisions)==1
            assert saved_calls < task.model_calls <= task.model_limit
            assert json.loads(task.steps[0].arguments)['caminho']==str(files[0])
            assert json.loads(task.steps[1].arguments)['caminho']==str(files[1])
            checks.extend(['shutdown_releases_store', 'history_reloaded', 'same_goal_resumed',
                'no_duplicate_read', 'candidate_reviewed_before_success', 'budget_retained'])
    elif scenario == 'denial':
        auren.permission_manager.policy['file.read'] = PermissionLevel.CONFIRM
        with application() as (worker, request, wait, snapshot):
            assert request('/api/message', {'text': f'Leia o arquivo {files[0]}.'})[0]==200
            value = wait(lambda v:any(e['kind']=='confirm' for e in v['events']))
            confirmation = next(e for e in value['events'] if e['kind']=='confirm')
            assert request('/api/confirm', {'id': confirmation['payload']['id'], 'approved': False})[0]==200
            value = wait(lambda v:v['tasks']['tasks'][0]['state']=='failed' and not v['busy'])
            task = worker._harness.current_task()
            assert task.state is TaskState.FAILED
            assert all(s.success is False and 'ALFA-731' not in s.result for s in task.steps)
            assert task.steps
            checks.extend(['factory_copies_stricter_policy', 'real_ui_confirmation_denied', 'file_content_not_read', 'failure_not_success'])
    elif scenario == 'routines':
        with application() as (worker, request, wait, snapshot):
            # Force the valid interleaving seen in Windows CI: storage commits
            # the occurrence before the UI notification is put on its queue.
            # The UI is asynchronous; both outcomes must eventually be observed.
            original_put = worker.events.put
            def gated_put(event, *args, **kwargs):
                if event.kind == 'notice' and 'Pendencia ficticia integrada' in event.text:
                    notice_ready.set()
                    assert publish_notice.wait(10)
                return original_put(event, *args, **kwargs)
            worker.events.put = gated_put
            value = snapshot()
            assert task_control(request, value, 'load')[0]==200
            value = wait(lambda v:bool(v['tasks'].get('chat_id')) and not v['busy'])
            chat_id = value['tasks']['chat_id']
            now = int(time.time())
            spec = {'kind':'reminder','objective':'Pendencia ficticia integrada', 'due_at':now,
                'expires_at':now+300,'interval_seconds':0,'max_runs':1}
            payload = {'action':'register','routine_id':'','spec':spec,'generation':value['generation']}
            assert request('/api/routine-action', payload)[0]==200
            value = wait(lambda v:bool(v['tasks']['routines']) and not v['busy'])
            routine = value['tasks']['routines'][0]
            assert routine['status']=='draft' and not requests
            assert request('/api/routine-action', dict(payload, action='authorize', routine_id=routine['id'], spec=None))[0]==200
            assert notice_ready.wait(10)
            value = wait(lambda v:v['tasks']['routines'][0]['status']=='exhausted')
            assert not any(e['kind']=='notice' and 'Pendencia ficticia integrada' in e['text'] for e in value['events'])
            assert len(value['notifications']) == 1
            notice = value['notifications'][0]
            assert notice['text'] == 'Pendencia ficticia integrada'
            publish_notice.set()
            value = wait(lambda v:any(e['kind']=='notice' and 'Pendencia ficticia integrada' in e['text'] for e in v['events']))
            assert value['tasks']['routines'][0]['status']=='exhausted'
            assert sum(e['kind']=='notice' and 'Pendencia ficticia integrada' in e['text'] for e in value['events'])==1
            assert not requests
            checks.extend(['routine_draft_separate_from_authorization', 'authorized_local_reminder_once', 'reminder_without_model'])
        with application() as (worker, request, wait, snapshot):
            value = snapshot()
            assert task_control(request, value, 'load')[0]==200
            value = wait(lambda v:chat_id in v['tasks'].get('chats', []) and not v['busy'])
            assert task_control(request, value, 'select', chat_id=chat_id)[0]==200
            value = wait(lambda v:v['tasks']['chat_id']==chat_id and bool(v['tasks']['routines']))
            assert value['tasks']['routines'][0]['status']=='exhausted'
            assert not requests
            assert value['notifications'] == [notice]
            assert request('/api/notification-action', {'action':'ack','id':notice['id'],
                'revision':notice['revision'],'chat_id':chat_id,'generation':value['generation']})[0] == 200
            assert snapshot()['notifications'] == []
            checks.extend(['pending_notice_survives_without_queue_or_ack', 'durable_ack_without_reexecuting_routine'])
            checks.append('completed_routine_survives_restart_without_replay')
    elif scenario == 'corrupt_database':
        db.write_bytes(b'not a database; synthetic fixture')
        before = db.read_bytes()
        with application() as (worker, request, wait, snapshot):
            assert task_control(request, snapshot(), 'load')[0]==200
            value = wait(lambda v:any(e['kind']=='error' for e in v['events']) and not v['busy'])
            assert not value['tasks']['tasks'] and not requests
            assert db.read_bytes()==before
            checks.extend(['corrupt_store_fails_closed', 'no_empty_replacement', 'no_model_call'])
    else:
        raise AssertionError('Unknown scenario')
    assert [p.read_bytes() for p in files]==originals
    output.write_text(json.dumps({'scenario':scenario,'checks':checks,'simulated_sdk_requests':len(requests),
        'real_api_calls':0,'personal_effects':0},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
