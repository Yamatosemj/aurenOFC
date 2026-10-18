"""Worker real e armazenamento ficticio; sem modelo ou dispositivos reais."""
from queue import Empty
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from ui.backend import AurenUiWorker


def factory(db):
    def make(confirmation_channel):
        pm = PermissionManager(confirmation_channel=confirmation_channel)
        return AurenHarness(task_manager=TaskManager(db_path=db), permission_manager=pm,
            criar_resposta=lambda *_: SimpleNamespace(output=[], output_text='Resultado ficticio recuperado.', usage=None),
            obter_chamadas=lambda r: r.output, executar_ferramenta=lambda _: pytest.fail('nao repetir efeito'),
            mostrar_uso=lambda: None, comando_rapido=lambda _: (False, ''),
            iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None, fechar=lambda: None)
    return make


def wait_for(worker, kind):
    for _ in range(30):
        event = worker.events.get(timeout=3)
        if event.kind == 'error':
            pytest.fail(event.text)
        if event.kind == kind:
            return event
    pytest.fail('evento esperado nao chegou')


def paused_goal(db):
    manager = TaskManager(db_path=db)
    task = manager.create('Qual o volume atual?', chat_id='owner')
    manager.start()
    manager.configure_model_budget(5)
    manager.begin_step('obter_audio_windows')
    manager.finish_step(success=True, result='Volume ficticio:20')
    manager.save_execution_checkpoint(PermissionManager().checkpoint_limits())
    manager.pause()
    manager.close()
    return task.task_id


def test_dispose_uses_complete_shutdown_and_releases_database(tmp_path):
    db = tmp_path/'close.sqlite3'
    paused_goal(db)
    worker = AurenUiWorker(harness_factory=factory(db))
    retained = factory(db)(SimpleNamespace(confirmar=lambda _: False))
    worker._harness = retained
    worker._dispose_harness()
    assert retained.task_manager.closed
    manager = TaskManager(db_path=db)
    try:
        assert manager.current_snapshot().state is TaskState.PAUSED
        assert manager.current_snapshot().cancel_requested is False
    finally:
        manager.close()


def test_worker_loads_selects_and_resumes_existing_goal_after_restart(tmp_path):
    db = tmp_path/'resume.sqlite3'
    task_id = paused_goal(db)
    worker = AurenUiWorker(harness_factory=factory(db))
    worker.start()
    try:
        worker.activate()
        assert worker.task_action('load', generation=worker.generation)
        wait_for(worker, 'tasks')
        assert 'owner' in worker.task_dashboard()['chats']
        assert worker.task_action('select', chat_id='owner', generation=worker.generation)
        wait_for(worker, 'tasks')
        data = worker.task_dashboard()
        assert data['chat_id'] == 'owner'
        assert data['tasks'][0]['task_id'] == task_id
        assert data['tasks'][0]['steps_done'] == 1
        assert worker.task_action('resume', chat_id='owner', task_id=task_id, generation=worker.generation)
        wait_for(worker, 'reply')
        wait_for(worker, 'idle')
        task = worker._harness.current_task()
        assert task.task_id == task_id and task.state is TaskState.COMPLETED
        assert len(task.steps) == 1 and task.model_calls == 1
    finally:
        worker.close()
        worker._thread.join(3)
    assert not worker.alive
    reopened = TaskManager(db_path=db)
    reopened.close()


def test_stale_task_controls_are_refused_before_execution(tmp_path):
    db = tmp_path/'stale.sqlite3'
    paused_goal(db)
    worker = AurenUiWorker(harness_factory=factory(db))
    worker.activate()
    old = worker.generation
    worker.go_off()
    worker.activate()
    assert worker.task_action('resume', chat_id='owner', task_id='fake', generation=old) is False
    assert worker._harness is None


def test_explicit_cancel_of_paused_goal_is_persisted(tmp_path):
    db = tmp_path/'cancel.sqlite3'
    task_id = paused_goal(db)
    worker = AurenUiWorker(harness_factory=factory(db))
    worker.start()
    try:
        worker.activate()
        worker.task_action('load', generation=worker.generation)
        wait_for(worker, 'tasks')
        assert worker.task_action('cancel', task_id=task_id, chat_id='owner', generation=worker.generation)
        assert worker._harness.task_manager.get_snapshot(task_id).state is TaskState.CANCELLED
    finally:
        worker.close()
        worker._thread.join(3)


def test_off_in_gap_before_goal_creation_prevents_provider_call(tmp_path):
    from threading import Event
    entered, release = Event(), Event()
    calls, created = [], []
    make = factory(tmp_path/'gap.sqlite3')
    def delayed_factory(**kwargs):
        h = make(**kwargs)
        original = h.processar_mensagem
        h.criar_resposta = lambda *_: calls.append('nao chamar modelo') or SimpleNamespace(output=[], output_text='fixture', usage=None)
        def delayed(text):
            entered.set()
            assert release.wait(3)
            return original(text)
        h.processar_mensagem = delayed
        created.append(h)
        return h
    worker = AurenUiWorker(harness_factory=delayed_factory)
    worker.start()
    try:
        worker.activate()
        worker.submit('oi')
        assert entered.wait(3)
        worker.go_off()
        release.set()
        wait_for(worker, 'off')
        assert calls == []
        assert created[0].current_task().state is TaskState.CANCELLED
    finally:
        release.set()
        worker.close()
        worker._thread.join(3)


def test_live_progress_and_pause_are_actual_persisted_states(tmp_path, monkeypatch):
    from threading import Event
    from tools import dispatcher
    from core.tool_result import ToolResult
    entered, release = Event(), Event()
    db = tmp_path/'progress.sqlite3'
    item = SimpleNamespace(type='function_call', name='obter_audio_windows', arguments='{}', call_id='read')
    def make(confirmation_channel):
        pm = PermissionManager(confirmation_channel=confirmation_channel)
        def model(*_):
            entered.set()
            assert release.wait(3)
            return SimpleNamespace(output=[item], output_text='', usage=None)
        return AurenHarness(task_manager=TaskManager(db_path=db), permission_manager=pm,
            criar_resposta=model, obter_chamadas=lambda r: r.output,
            executar_ferramenta=lambda call: dispatcher.executar_ferramenta(call, pm, None),
            mostrar_uso=lambda: None, comando_rapido=lambda _: (False, ''),
            iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None, fechar=lambda: None)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name, lambda *_: ToolResult.success('Volume ficticio:20'))
    worker = AurenUiWorker(harness_factory=make)
    worker.start()
    try:
        worker.activate()
        worker.submit('Consulte o volume e depois consulte o status.')
        assert entered.wait(3)
        data = worker.task_dashboard()
        task = data['tasks'][0]
        assert task['state'] == 'waiting' and task['model_calls'] == 1 and task['steps_done'] == 0
        assert worker.task_action('pause', chat_id=data['chat_id'], task_id=task['task_id'], generation=data['generation'])
        release.set()
        wait_for(worker, 'idle')
        data = worker.task_dashboard()['tasks'][0]
        assert data['state'] == 'paused' and data['steps_done'] == 1 and data['can_resume'] is True
    finally:
        release.set()
        worker.close()
        worker._thread.join(3)
    manager = TaskManager(db_path=db)
    try:
        assert manager.current_snapshot().state is TaskState.PAUSED
        assert not manager.current_snapshot().cancel_requested
    finally:
        manager.close()


def test_interface_registration_does_not_authorize_routine(tmp_path):
    import time
    worker = AurenUiWorker(harness_factory=factory(tmp_path/'routines.sqlite3'))
    worker.start()
    try:
        worker.activate()
        worker.task_action('load', generation=worker.generation)
        wait_for(worker, 'tasks')
        now = int(time.time())
        spec = {'kind': 'read_status', 'objective': '', 'due_at': now+3600, 'expires_at': now+7200,
                'interval_seconds': 0, 'max_runs': 1}
        assert worker.routine_action('register', spec=spec, generation=worker.generation)
        wait_for(worker, 'tasks')
        routine = worker.task_dashboard()['routines'][0]
        assert routine['status'] == 'draft' and routine['model_budget'] == 1
        assert worker.routine_action('authorize', routine_id=routine['id'], generation=worker.generation)
        wait_for(worker, 'tasks')
        assert worker.task_dashboard()['routines'][0]['status'] == 'enabled'
        assert worker.routine_action('revoke', routine_id=routine['id'], generation=worker.generation)
        assert worker.task_dashboard()['routines'][0]['status'] == 'revoked'
    finally:
        worker.close()
        worker._thread.join(3)


def test_http_task_controls_require_token_schema_and_current_generation():
    from ui.chrome_server import LocalChromeApp, ChromeServer
    from threading import Thread
    from http.client import HTTPConnection
    from queue import Queue
    import json
    calls = []
    worker = SimpleNamespace(events=Queue(), generation=3, start=lambda: None, close=lambda: None,
        activate=lambda: None, task_dashboard=lambda: {}, task_action=lambda **kw: calls.append(kw) or True)
    app = LocalChromeApp(worker)
    server = ChromeServer(app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(payload, token):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request('POST', '/api/task-action', json.dumps(payload),
                {'Content-Type':'application/json', 'X-Auren-Token':token})
            answer = connection.getresponse()
            answer.read()
            return answer.status
        finally:
            connection.close()
    try:
        body = {'action':'load', 'task_id':'', 'chat_id':'', 'generation':3}
        assert request(body, '') == 403
        assert request(dict(body, extra=True), app.token) == 400
        assert request(dict(body, generation=2), app.token) == 400
        assert calls == []
        assert request(body, app.token) == 200
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
        thread.join(3)
