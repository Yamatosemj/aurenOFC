"""Durable delivery with real SQLite, fake time and effects; no API."""
from types import SimpleNamespace
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from core.routines import RoutineScheduler
from core.task_manager import TaskManager, TaskState


def reminder(service, *, execute=False):
    routine = service.register(chat_id='owner', objective='Estudar exemplo ficticio',
        due_at=100, expires_at=1000, mode='execute' if execute else 'suggest',
        allowed_calls=[{'name': 'obter_audio_windows', 'arguments': {}}] if execute else [],
        model_budget=1 if execute else 0)
    service.authorize(routine['id'], chat_id='owner')
    return routine


def test_pending_delivery_survives_restart_and_ack_is_durable(tmp_path):
    db = tmp_path/'tasks.sqlite3'
    manager = TaskManager(db_path=db)
    service = RoutineScheduler(manager, clock=lambda: 100)
    routine = reminder(service)
    service.tick(None, chat_id='owner')  # No consumer sees the returned event.
    first = service.pending_notifications(chat_id='owner')[0]
    assert service.pending_notifications(chat_id='other') == []
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = RoutineScheduler(manager, clock=lambda: 2000)  # Past original routine expiry.
        assert service.pending_notifications(chat_id='owner') == [first]
        assert service.tick(None, chat_id='owner') == []
        assert service.get(routine['id'], chat_id='owner')['runs_left'] == 0
        with pytest.raises(RuntimeError):
            service.acknowledge_notification(first['id'], first['revision'], chat_id='other')
        assert service.acknowledge_notification(first['id'], first['revision'], chat_id='owner')
        assert service.acknowledge_notification(first['id'], first['revision'], chat_id='owner')
        assert service.pending_notifications(chat_id='owner') == []
    finally:
        manager.close()
    manager = TaskManager(db_path=db)
    try:
        assert RoutineScheduler(manager).pending_notifications(chat_id='owner') == []
    finally:
        manager.close()


def test_notification_write_failure_rolls_back_occurrence(tmp_path):
    manager = TaskManager(db_path=tmp_path/'atomic.sqlite3')
    try:
        service = RoutineScheduler(manager, clock=lambda: 100)
        routine = reminder(service)
        manager._storage.connection.execute('''CREATE TRIGGER reject_notice
            BEFORE INSERT ON auren_routine_notifications BEGIN SELECT RAISE(ABORT,'fixture'); END''')
        manager._storage.connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            service.tick(None, chat_id='owner')
        saved = service.get(routine['id'], chat_id='owner')
        assert saved['status'] == 'enabled' and saved['runs_left'] == 1
        manager._storage.connection.execute('DROP TRIGGER reject_notice')
        manager._storage.connection.commit()
        service.tick(None, chat_id='owner')
        assert len(service.pending_notifications(chat_id='owner')) == 1
    finally:
        manager.close()


def test_failed_ack_write_keeps_notice_pending(tmp_path):
    manager = TaskManager(db_path=tmp_path/'ack-failure.sqlite3')
    try:
        service = RoutineScheduler(manager, clock=lambda: 100)
        reminder(service)
        service.tick(None, chat_id='owner')
        notice = service.pending_notifications(chat_id='owner')[0]
        manager._storage.connection.execute('''CREATE TRIGGER reject_ack BEFORE UPDATE
            ON auren_routine_notifications BEGIN SELECT RAISE(ABORT,'fixture'); END''')
        manager._storage.connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            service.acknowledge_notification(notice['id'], notice['revision'], chat_id='owner')
        assert service.pending_notifications(chat_id='owner') == [notice]
    finally:
        manager.close()


def test_snooze_persists_and_late_ack_cannot_discard_new_delivery(tmp_path):
    db = tmp_path/'snooze.sqlite3'
    now = [100]
    manager = TaskManager(db_path=db)
    service = RoutineScheduler(manager, clock=lambda: now[0])
    routine = reminder(service)
    service.tick(None, chat_id='owner')
    notice = service.pending_notifications(chat_id='owner')[0]
    service.acknowledge_notification(notice['id'], notice['revision'], chat_id='owner')
    service.snooze_notification(notice['id'], notice['revision'], chat_id='owner', seconds=600)
    assert not service.acknowledge_notification(notice['id'], notice['revision'], chat_id='owner')
    assert service.pending_notifications(chat_id='owner') == []
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = RoutineScheduler(manager, clock=lambda: now[0])
        now[0] = 699
        assert service.pending_notifications(chat_id='owner') == []
        now[0] = 700
        delayed = service.pending_notifications(chat_id='owner')[0]
        assert delayed['revision'] == notice['revision'] + 1
        assert delayed['available_at'] == 700
        assert service.tick(None, chat_id='owner') == []
        assert service.get(routine['id'], chat_id='owner')['runs_left'] == 0
    finally:
        manager.close()


def test_uncertain_execution_recovers_as_notice_without_repeating_effect(tmp_path):
    db = tmp_path/'crash.sqlite3'
    manager = TaskManager(db_path=db)
    service = RoutineScheduler(manager, clock=lambda: 100)
    routine = reminder(service, execute=True)
    effects = []
    def crash(*a, **k):
        effects.append('effect')
        raise SystemExit(17)
    h = SimpleNamespace(task_manager=manager, _garantir_sessao_chat=lambda: 'owner',
        processar_mensagem=crash)
    with pytest.raises(SystemExit):
        service.tick(h, chat_id='owner')
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = RoutineScheduler(manager, clock=lambda: 101)
        notice = service.pending_notifications(chat_id='owner')[0]
        assert notice['kind'] == 'interrupted'
        assert service.tick(None, chat_id='owner') == []
        assert service.get(routine['id'], chat_id='owner')['status'] == 'interrupted'
        service.acknowledge_notification(notice['id'], notice['revision'], chat_id='owner')
        assert effects == ['effect']
    finally:
        manager.close()


def test_completed_execution_notification_can_repeat_without_model_or_effect(tmp_path):
    manager = TaskManager(db_path=tmp_path/'execute.sqlite3')
    try:
        service = RoutineScheduler(manager, clock=lambda: 100)
        reminder(service, execute=True)
        effects = []
        h = SimpleNamespace(task_manager=manager, _garantir_sessao_chat=lambda: 'owner',
            processar_mensagem=lambda *a, **k: effects.append('once'),
            current_task=lambda: SimpleNamespace(task_id='fictitious', state=TaskState.COMPLETED,
                steps=[SimpleNamespace(success=True)]))
        service.tick(h, chat_id='owner')
        first = service.pending_notifications(chat_id='owner')
        assert first[0]['kind'] == 'completed'
        for _ in range(3):
            assert service.tick(h, chat_id='owner') == []
            assert service.pending_notifications(chat_id='owner') == first
        assert effects == ['once']
    finally:
        manager.close()


def test_notification_does_not_present_unverified_model_text_as_completed(tmp_path):
    from core.harness import AurenHarness
    from core.harness_runtime import SessionContext
    from core.permission_manager import PermissionManager
    manager = TaskManager(db_path=tmp_path/'unverified.sqlite3')
    pm = PermissionManager()
    h = AurenHarness(task_manager=manager, permission_manager=pm,
        criar_resposta=lambda *a: SimpleNamespace(output=[],
            output_text='O arquivo contém: `CODIGO_FICTICIO_Z73: 19 itens.`', usage=None),
        obter_chamadas=lambda r:r.output, executar_ferramenta=lambda c:pytest.fail('No effect expected'),
        mostrar_uso=lambda:None, comando_rapido=lambda _:(False,''),
        iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None, fechar=lambda:None)
    h._session = SessionContext('owner', tmp_path/'chat.log')
    try:
        service = RoutineScheduler(manager, clock=lambda:100)
        r = service.register(chat_id='owner', objective='Leia arquivo ficticio', due_at=100,
            expires_at=1000, mode='execute', allowed_calls=[{'name':'ler_arquivo',
                'arguments':{'caminho':'ficticio.txt','inicio':0,'limite_caracteres':200}}], model_budget=2)
        service.authorize(r['id'], chat_id='owner')
        assert service.tick(h, chat_id='owner')[0]['kind'] == 'failed'
        assert service.pending_notifications(chat_id='owner')[0]['kind'] == 'failed'
        assert service.get(r['id'], chat_id='owner')['status'] == 'failed'
        # The Harness now rejects the unsupported completion before publication.
        assert h.current_task().state is TaskState.FAILED and not h.current_task().steps
        assert service.tick(h, chat_id='owner') == []
    finally:
        h.shutdown()


@pytest.mark.parametrize('mode,exit_code,kind', [('reminder',17,'suggestion'), ('uncertain',21,'interrupted')])
def test_real_process_death_keeps_delivery_and_never_replays_effect(tmp_path, mode, exit_code, kind):
    directory = tmp_path/mode
    child = subprocess.run([sys.executable, '-B', '-m', 'remote_tests.notification_crash_fixture',
        mode, str(directory)], cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=15)
    assert child.returncode == exit_code, child.stderr
    manager = TaskManager(db_path=directory/'tasks.sqlite3')
    try:
        service = RoutineScheduler(manager, clock=lambda: 101)
        pending = service.pending_notifications(chat_id='owner')
        assert len(pending) == 1 and pending[0]['kind'] == kind
        assert service.tick(None, chat_id='owner') == []
        assert service.pending_notifications(chat_id='owner') == pending
        if mode == 'uncertain':
            assert (directory/'effects.txt').read_bytes() == b'one fictitious effect\n'
    finally:
        manager.close()


def test_existing_routines_upgrade_without_reauthorizing_or_losing_schedule(tmp_path):
    db = tmp_path/'old.sqlite3'
    manager = TaskManager(db_path=db)
    service = RoutineScheduler(manager, clock=lambda: 99)
    routine = reminder(service)
    manager._storage.connection.execute('DROP TABLE auren_routine_notifications')
    manager._storage.connection.commit()  # Same schema that #162 used.
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = RoutineScheduler(manager, clock=lambda: 100)
        assert service.get(routine['id'], chat_id='owner')['status'] == 'enabled'
        assert service.pending_notifications(chat_id='owner') == []
        service.tick(None, chat_id='owner')
        assert len(service.pending_notifications(chat_id='owner')) == 1
    finally:
        manager.close()


@pytest.mark.parametrize('revision', [True, 0, -1, '1'])
def test_invalid_revision_cannot_acknowledge(tmp_path, revision):
    manager = TaskManager(db_path=tmp_path/'invalid.sqlite3')
    try:
        service = RoutineScheduler(manager, clock=lambda: 100)
        reminder(service)
        service.tick(None, chat_id='owner')
        notice = service.pending_notifications(chat_id='owner')[0]
        with pytest.raises(ValueError):
            service.acknowledge_notification(notice['id'], revision, chat_id='owner')
        assert service.pending_notifications(chat_id='owner') == [notice]
    finally:
        manager.close()
