"""Persistencia real em SQLite e subprocessos; somente dados ficticios."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agent.planner import PlanBuilder
from core.task_manager import TaskManager, TaskState
from core.permission_manager import PermissionManager
from core.tool_result import ToolResult
from tools import dispatcher


def test_checkpoint_plan_steps_and_journal_survive_restart(tmp_path):
    db = tmp_path/'tasks.sqlite3'
    manager = TaskManager(db_path=db)
    plan = PlanBuilder.build('abra a calculadora e depois consulte o volume')
    task = manager.create(plan.objective, chat_id='chat-ficticio', plan=plan)
    manager.start()
    manager.begin_step('obter_audio_windows', '{}')
    manager.finish_step(success=True, result='volume ficticio 30')
    manager.close()
    recovered = TaskManager(db_path=db)
    try:
        snapshot = recovered.get_snapshot(task.task_id)
        assert snapshot.state is TaskState.INTERRUPTED
        assert snapshot.plan == plan and snapshot.steps[0].success is True
        assert snapshot.steps[0].result == 'volume ficticio 30'
        assert recovered.resume_checkpoint(task.task_id).state is TaskState.RUNNING
        operations = [event['operation'] for event in recovered.execution_history(task.task_id)]
        assert operations == ['create', 'start', 'begin_step', 'finish_step', 'recover', 'resume_checkpoint']
    finally:
        recovered.close()


@pytest.mark.parametrize('unfinished', [False, True])
def test_real_process_crash_releases_lock_and_preserves_uncertainty(tmp_path, unfinished):
    db = tmp_path/'crash.sqlite3'
    source = """
import os, sys
from pathlib import Path
from core.task_manager import TaskManager
m = TaskManager(db_path=sys.argv[1])
t = m.create('objetivo ficticio', chat_id='chat', task_id='crash')
m.start()
m.begin_step('ferramenta_ficticia', '{}')
Path(sys.argv[2]).write_text('efeito ficticio executado uma vez')
if sys.argv[3] == 'False':
    m.finish_step(success=True, result='efeito confirmado')
os._exit(17)
"""
    effect = tmp_path/'effect.txt'
    result = subprocess.run([sys.executable, '-B', '-c', source, str(db), str(effect), str(unfinished)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), timeout=15,
        capture_output=True, text=True)
    assert result.returncode == 17, result.stderr
    recovered = TaskManager(db_path=db)
    try:
        assert recovered.get_snapshot('crash').state is TaskState.INTERRUPTED
        before = recovered.get_snapshot('crash')
        if unfinished:
            with pytest.raises(RuntimeError, match='incert'):
                recovered.resume_checkpoint('crash')
            with pytest.raises(RuntimeError):
                recovered.complete('nao pode concluir')
            with pytest.raises(RuntimeError):
                recovered.finish_step(success=True, result='nao pode inventar resultado apos reinicio')
            assert recovered.get_snapshot('crash') == before
        else:
            assert recovered.resume_checkpoint('crash').state is TaskState.RUNNING
        assert effect.read_text() == 'efeito ficticio executado uma vez'
    finally:
        recovered.close()


def test_second_writer_is_refused_without_overwriting_first(tmp_path):
    db = tmp_path/'owned.sqlite3'
    manager = TaskManager(db_path=db)
    try:
        task = manager.create('objetivo ficticio', chat_id='a')
        for _ in range(2):
            with pytest.raises(RuntimeError, match='uso'):
                TaskManager(db_path=db)
        assert manager.get_snapshot(task.task_id).objective == 'objetivo ficticio'
    finally:
        manager.close()


def test_write_failure_rolls_back_before_new_effect(tmp_path, monkeypatch):
    manager = TaskManager(db_path=tmp_path/'fail.sqlite3')
    try:
        manager.create('objetivo ficticio', chat_id='a')
        manager.start()
        before = manager.current_snapshot()
        def fail(*args, **kwargs):
            raise sqlite3.OperationalError('disco ficticio indisponivel')
        monkeypatch.setattr(manager._storage, 'save', fail)
        with pytest.raises(sqlite3.OperationalError):
            manager.begin_step('ferramenta_ficticia')
        assert manager.current_snapshot() == before
    finally:
        manager.close()


def test_pause_and_terminal_states_are_preserved(tmp_path):
    db = tmp_path/'paused.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('objetivo ficticio', chat_id='a')
    manager.start()
    assert manager.pause().state is TaskState.PAUSED
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        assert manager.get_snapshot(task.task_id).state is TaskState.PAUSED
        manager.resume_checkpoint(task.task_id)
        manager.complete('verificado ficticio')
        before = manager.current_snapshot()
        with pytest.raises(RuntimeError):
            manager.resume_checkpoint(task.task_id)
        assert manager.current_snapshot() == before
    finally:
        manager.close()


def test_archived_task_remains_accessible_after_memory_pruning(tmp_path):
    manager = TaskManager(db_path=tmp_path/'archive.sqlite3', max_history=1)
    try:
        first = manager.create('primeiro ficticio', chat_id='a')
        manager.start()
        manager.complete('ok')
        manager.create('segundo ficticio', chat_id='b')
        assert manager.get_snapshot(first.task_id).state is TaskState.COMPLETED
        assert not manager.recent_snapshots(None)
        assert all(s.chat_id == 'a' for s in manager.recent_snapshots('a'))
    finally:
        manager.close()


@pytest.mark.parametrize('future', [False, True])
def test_invalid_database_does_not_silently_start_empty(tmp_path, future):
    db = tmp_path/'invalid.sqlite3'
    if future:
        with sqlite3.connect(db) as connection:
            connection.execute('PRAGMA user_version=999')
    else:
        db.write_bytes(b'nao e banco sqlite')
    before = db.read_bytes()
    with pytest.raises((RuntimeError, sqlite3.DatabaseError)):
        TaskManager(db_path=db)
    assert db.read_bytes() == before


def test_resume_does_not_restore_permission_for_following_step(tmp_path, monkeypatch):
    db = tmp_path/'permissions.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('abra o executavel ficticio depois de consultar o audio', chat_id='a')
    manager.start()
    manager.begin_step('obter_audio_windows', '{}')
    manager.finish_step(success=True, result='audio ficticio consultado')
    manager.close()
    recovered = TaskManager(db_path=db)
    effects, confirmations = [], []
    try:
        recovered.resume_checkpoint(task.task_id)
        permissions = PermissionManager(confirmation_channel=SimpleNamespace(
            confirmar=lambda request: confirmations.append(request) or False))
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'abrir_programa',
            lambda *args: effects.append(args) or ToolResult.success('Nunca executar.'))
        call = SimpleNamespace(name='abrir_programa', arguments=json.dumps({'programa':r'C:\Ficticio\Editor.exe'}))
        result = dispatcher.executar_ferramenta(call, permissions, None)
        assert not result.ok and len(confirmations) == 1 and effects == []
        assert recovered.current_snapshot().steps[0].success is True
    finally:
        recovered.close()


def test_resume_cannot_replace_another_running_task(tmp_path):
    manager = TaskManager(db_path=tmp_path/'active.sqlite3')
    try:
        first = manager.create('primeiro ficticio', chat_id='a')
        manager.start()
        manager.pause()
        manager.clear_current()
        second = manager.create('segundo ficticio', chat_id='b')
        manager.start()
        before = manager.current_snapshot()
        with pytest.raises(RuntimeError):
            manager.resume_checkpoint(first.task_id)
        assert manager.current_snapshot() == before and before.task_id == second.task_id
    finally:
        manager.close()


def test_previous_failed_effect_does_not_disappear_after_restart(tmp_path):
    db = tmp_path/'failed-effect.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('objetivo ficticio', chat_id='a')
    manager.start()
    manager.begin_step('ferramenta_ficticia')
    manager.finish_step(success=False, error='resultado nao comprovado')
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        with pytest.raises(RuntimeError):
            manager.resume_checkpoint(task.task_id)
        assert manager.current_snapshot().state is TaskState.INTERRUPTED
    finally:
        manager.close()


def test_hard_link_alias_cannot_acquire_a_second_writer(tmp_path):
    db = tmp_path/'owner.sqlite3'
    manager = TaskManager(db_path=db)
    second = None
    try:
        alias = tmp_path/'alias.sqlite3'
        try:
            os.link(db, alias)
        except OSError:
            pytest.skip('Sistema de arquivos nao permite hard links na fixture.')
        with pytest.raises(RuntimeError):
            second = TaskManager(db_path=alias)
    finally:
        if second is not None:
            second.close()
        manager.close()


@pytest.mark.parametrize('operation', ['begin_step', 'finish_step'])
def test_sql_transaction_failure_preserves_last_confirmed_checkpoint(tmp_path, operation):
    db = tmp_path/'transaction.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('objetivo ficticio', chat_id='a')
    manager.start()
    if operation == 'finish_step':
        manager.begin_step('ferramenta_ficticia')
    before = manager.current_snapshot()
    connection = manager._storage.connection
    connection.execute("CREATE TRIGGER refuse_event BEFORE INSERT ON task_events BEGIN SELECT RAISE(ABORT, 'falha ficticia'); END")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            if operation == 'begin_step':
                manager.begin_step('ferramenta_ficticia')
            else:
                manager.finish_step(success=True, result='nao deve aparecer como gravado')
        assert manager.current_snapshot() == before
    finally:
        connection.execute('DROP TRIGGER refuse_event')
        connection.commit()
        manager.close()
    recovered = TaskManager(db_path=db)
    try:
        restored = recovered.get_snapshot(task.task_id)
        assert restored.steps == before.steps
        assert restored.state is TaskState.INTERRUPTED
        if operation == 'finish_step':
            with pytest.raises(RuntimeError):
                recovered.resume_checkpoint(task.task_id)
    finally:
        recovered.close()


@pytest.mark.parametrize('storage_fails', [False, True])
def test_harness_uses_durable_checkpoint_before_dispatch_and_releases_store(tmp_path, monkeypatch, storage_fails):
    from core.harness import AurenHarness
    db = tmp_path/'harness.sqlite3'
    manager = TaskManager(db_path=db)
    permissions = PermissionManager()
    effects = []
    call = SimpleNamespace(type='function_call', name='obter_audio_windows', arguments='{}', call_id='audio')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, call.name,
        lambda *args: effects.append('efeito ficticio') or ToolResult.success('Volume ficticio: 30'))
    save = manager._storage.save
    def save_checkpoint(records, selected, operation, previous):
        if storage_fails and operation == 'begin_step':
            raise sqlite3.OperationalError('falha ficticia de checkpoint')
        return save(records, selected, operation, previous)
    monkeypatch.setattr(manager._storage, 'save', save_checkpoint)
    harness = AurenHarness(task_manager=manager,
        criar_resposta=lambda *_: SimpleNamespace(output=[call], output_text='', usage=None),
        executar_ferramenta=lambda item: dispatcher.executar_ferramenta(item, permissions, None),
        mostrar_uso=lambda: None, obter_chamadas=lambda response: response.output,
        comando_rapido=lambda _: (False, ''), iniciar_tarefa=permissions.iniciar_tarefa,
        apos_tarefa=None, fechar=lambda: None, max_model_rounds=1)
    try:
        if storage_fails:
            with pytest.raises(sqlite3.OperationalError):
                harness.processar_mensagem('Qual o volume atual?')
            assert effects == [] and manager.current_snapshot().steps == ()
        else:
            harness.processar_mensagem('Qual o volume atual?')
            assert effects == ['efeito ficticio']
            assert manager.current_snapshot().state is TaskState.COMPLETED
        snapshot = manager.current_snapshot()
        assert snapshot.plan is not None
    finally:
        harness.shutdown()
    recovered = TaskManager(db_path=db)
    try:
        restored = recovered.get_snapshot(snapshot.task_id)
        assert restored.plan == snapshot.plan and restored.steps == snapshot.steps
    finally:
        recovered.close()


@pytest.mark.parametrize('kind', ['empty_file', 'foreign_database'])
def test_existing_unrecognized_file_is_not_initialized_as_empty_history(tmp_path, kind):
    db = tmp_path/'unrecognized.sqlite3'
    if kind == 'empty_file':
        db.touch()
    else:
        with sqlite3.connect(db) as connection:
            connection.execute('CREATE TABLE unrelated (value TEXT)')
            connection.execute("INSERT INTO unrelated VALUES ('dado ficticio')")
    before = db.read_bytes()
    unexpected = None
    try:
        with pytest.raises(RuntimeError):
            unexpected = TaskManager(db_path=db)
    finally:
        if unexpected is not None:
            unexpected.close()
    assert db.read_bytes() == before


def test_archived_objectives_can_be_listed_without_mixing_chats(tmp_path):
    db = tmp_path/'list.sqlite3'
    manager = TaskManager(db_path=db, max_history=1)
    for index, chat in enumerate(['a', 'b', 'a']):
        manager.create(f'objetivo ficticio {index}', chat_id=chat, task_id=str(index))
        manager.start()
        manager.complete('ok ficticio')
    manager.close()
    manager = TaskManager(db_path=db, max_history=1)
    try:
        assert [s.task_id for s in manager.list_snapshots('a')] == ['2', '0']
        assert [s.task_id for s in manager.list_snapshots('a', limit=1, offset=1)] == ['0']
        assert [s.task_id for s in manager.list_snapshots('b')] == ['1']
        assert manager.list_snapshots(None) == ()
    finally:
        manager.close()


def test_legacy_shortcut_cannot_execute_before_a_durable_checkpoint(tmp_path, monkeypatch):
    from core.harness import AurenHarness
    manager = TaskManager(db_path=tmp_path/'shortcut.sqlite3')
    save = manager._storage.save
    effects = []
    def refuse_step(records, selected, operation, previous):
        if operation == 'begin_step':
            raise sqlite3.OperationalError('checkpoint ficticio recusado')
        return save(records, selected, operation, previous)
    monkeypatch.setattr(manager._storage, 'save', refuse_step)
    call = SimpleNamespace(type='function_call', name='obter_audio_windows', arguments='{}', call_id='read')
    harness = AurenHarness(task_manager=manager,
        criar_resposta=lambda *_: SimpleNamespace(output=[call], output_text='', usage=None),
        executar_ferramenta=lambda _: effects.append('ferramenta') or ToolResult.success('feito'),
        mostrar_uso=lambda: None, obter_chamadas=lambda response: response.output,
        comando_rapido=lambda _: effects.append('atalho') or (True, 'feito'),
        iniciar_tarefa=lambda: None, apos_tarefa=None, fechar=lambda: None)
    try:
        with pytest.raises(sqlite3.OperationalError):
            harness.processar_mensagem('Qual o volume atual?')
        assert effects == []
    finally:
        harness.shutdown()


def test_shutdown_keeps_a_paused_checkpoint_resumable(tmp_path):
    from core.harness import AurenHarness
    db = tmp_path/'shutdown.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('objetivo ficticio', chat_id='a')
    manager.start()
    manager.pause()
    harness = AurenHarness(task_manager=manager,
        criar_resposta=lambda *_: pytest.fail('Nao deve consultar modelo.'),
        executar_ferramenta=lambda _: pytest.fail('Nao deve executar ferramenta.'),
        mostrar_uso=lambda: None, obter_chamadas=lambda _: [],
        comando_rapido=lambda _: (False, ''), iniciar_tarefa=lambda: None,
        apos_tarefa=None, fechar=lambda: None)
    harness.shutdown()
    recovered = TaskManager(db_path=db)
    try:
        assert recovered.resume_checkpoint(task.task_id).state is TaskState.RUNNING
    finally:
        recovered.close()


@pytest.mark.parametrize('field', ['success', 'cancel_requested', 'finished_at', 'max_rounds'])
def test_malformed_checkpoint_cannot_claim_a_confirmed_step(tmp_path, field):
    db = tmp_path/'malformed.sqlite3'
    manager = TaskManager(db_path=db)
    plan = PlanBuilder.build('objetivo ficticio')
    task = manager.create(plan.objective, chat_id='a', plan=plan)
    manager.start()
    manager.begin_step('ferramenta_ficticia')
    manager.finish_step(success=True, result='resultado ficticio')
    manager.close()
    with sqlite3.connect(db) as connection:
        payload = json.loads(connection.execute('SELECT payload FROM tasks').fetchone()[0])
        if field in {'success', 'finished_at'}:
            payload['steps'][0][field] = 'nao confirmado' if field == 'success' else None
        elif field == 'max_rounds':
            payload['plan'][field] = 'sem limite'
        else:
            payload[field] = 0
        connection.execute('UPDATE tasks SET payload=? WHERE task_id=?', (json.dumps(payload), task.task_id))
    unexpected = None
    try:
        with pytest.raises(RuntimeError):
            unexpected = TaskManager(db_path=db)
    finally:
        if unexpected is not None:
            unexpected.close()


def test_live_process_cannot_take_over_an_owned_database(tmp_path):
    db = tmp_path/'exclusive.sqlite3'
    manager = TaskManager(db_path=db)
    source = """
import sys
from core.task_manager import TaskManager
try:
    manager = TaskManager(db_path=sys.argv[1])
except RuntimeError as error:
    if 'uso' not in str(error):
        raise
    raise SystemExit(23)
manager.close()
"""
    try:
        task = manager.create('objetivo ficticio', chat_id='a')
        result = subprocess.run([sys.executable, '-B', '-c', source, str(db)],
            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), timeout=15,
            capture_output=True, text=True)
        assert result.returncode == 23, result.stderr
        assert manager.start(task.task_id).state is TaskState.RUNNING
    finally:
        manager.close()
