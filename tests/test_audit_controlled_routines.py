"""Rotinas com relogio controlado e SQLite real, sem API ou efeitos pessoais."""
from types import SimpleNamespace
import json

import pytest

from core.task_manager import TaskManager, TaskState
from core.permission_manager import PermissionManager, PermissionLevel
from core.tool_result import ToolResult
from core.harness import AurenHarness
from tools import dispatcher


def scheduler(manager, clock):
    from core.routines import RoutineScheduler
    return RoutineScheduler(manager, clock=lambda: clock[0])


def register(service, **extra):
    return service.register(chat_id='owner', objective='Consulte o volume.', due_at=100,
        expires_at=1000, interval_seconds=60, max_runs=2, **extra)


def test_suggestions_require_approval_and_survive_restart_without_duplicate(tmp_path):
    db = tmp_path/'routines.sqlite3'
    clock = [100]
    manager = TaskManager(db_path=db)
    service = scheduler(manager, clock)
    routine = register(service)
    assert service.tick(None, chat_id='owner') == []
    service.authorize(routine['id'], chat_id='owner')
    assert service.tick(None, chat_id='other') == []
    assert service.tick(None, chat_id='owner')[0]['kind'] == 'suggestion'
    assert service.tick(None, chat_id='owner') == []
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = scheduler(manager, clock)
        assert service.tick(None, chat_id='owner') == []
        clock[0] = 900  # Sem despejar disparos atrasados.
        assert len(service.tick(None, chat_id='owner')) == 1
        assert service.tick(None, chat_id='owner') == []
        assert service.get(routine['id'], chat_id='owner')['status'] == 'exhausted'
    finally:
        manager.close()


def test_revocation_and_chat_scope_are_enforced(tmp_path):
    manager = TaskManager(db_path=tmp_path/'revoke.sqlite3')
    try:
        service = scheduler(manager, [100])
        routine = register(service)
        with pytest.raises(RuntimeError):
            service.authorize(routine['id'], chat_id='other')
        service.authorize(routine['id'], chat_id='owner')
        service.revoke(routine['id'], chat_id='owner')
        assert service.tick(None, chat_id='owner') == []
        with pytest.raises(RuntimeError):
            service.authorize(routine['id'], chat_id='owner')
    finally:
        manager.close()


def test_crash_after_claim_is_not_retried_automatically(tmp_path):
    db = tmp_path/'crash.sqlite3'
    manager = TaskManager(db_path=db)
    service = scheduler(manager, [100])
    routine = register(service, mode='execute', allowed_calls=[{'name': 'obter_audio_windows', 'arguments': {}}], model_budget=1)
    service.authorize(routine['id'], chat_id='owner')
    effects = []
    def crash(*args, **kwargs):
        effects.append('efeito ficticio')
        raise SystemExit(17)
    with pytest.raises(SystemExit):
        service.tick(SimpleNamespace(processar_mensagem=crash, task_manager=manager,
            _garantir_sessao_chat=lambda: 'owner'), chat_id='owner')
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        service = scheduler(manager, [200])
        assert service.tick(SimpleNamespace(processar_mensagem=crash), chat_id='owner') == []
        assert effects == ['efeito ficticio']
        assert service.get(routine['id'], chat_id='owner')['status'] == 'interrupted'
    finally:
        manager.close()


@pytest.mark.parametrize('reason', ['outside_scope', 'denied', 'revoked', 'expired'])
def test_routine_grant_never_bypasses_dispatch_or_late_revocation(tmp_path, monkeypatch, reason):
    manager = TaskManager(db_path=tmp_path/'scope.sqlite3')
    clock = [100]
    service = scheduler(manager, clock)
    routine = register(service, mode='execute', allowed_calls=[
        {'name': 'definir_volume_windows', 'arguments': {'percentual': 35}}], model_budget=4)
    service.authorize(routine['id'], chat_id='owner')
    effects, confirmations = [], []
    def confirm(request):
        confirmations.append(request)
        if reason == 'revoked':
            service.revoke(routine['id'], chat_id='owner')
        if reason == 'expired':
            clock[0] = 1001
        return reason != 'denied'  # Somente canal ficticio; sem efeito real.
    pm = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=confirm))
    pm.policy['windows.audio.control'] = PermissionLevel.CONFIRM
    item = SimpleNamespace(type='function_call', name='definir_volume_windows',
        arguments=json.dumps({'percentual': 99 if reason == 'outside_scope' else 35}), call_id='volume')
    responses = [SimpleNamespace(output=[item], output_text='', usage=None),
                 SimpleNamespace(output=[], output_text='fim', usage=None)]
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name,
        lambda *_: effects.append('nao executar') or ToolResult.success('efeito ficticio'))
    h = AurenHarness(task_manager=manager, permission_manager=pm,
        criar_resposta=lambda *_: responses.pop(0), obter_chamadas=lambda r: r.output,
        executar_ferramenta=lambda call: dispatcher.executar_ferramenta(call, pm, None),
        mostrar_uso=lambda: None, comando_rapido=lambda _: (False, ''),
        iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None, fechar=lambda: None, max_model_rounds=3)
    from core.harness_runtime import SessionContext
    h._session = SessionContext('owner', tmp_path/'chat'/'chat.log')
    try:
        service.tick(h, chat_id='owner')
        assert effects == []
        assert len(confirmations) == (0 if reason == 'outside_scope' else 1)
        assert h.current_task().state is TaskState.FAILED
        assert h.current_task().model_calls <= 4
    finally:
        h.shutdown()


def test_invalid_or_unbounded_grant_is_rejected(tmp_path):
    manager = TaskManager(db_path=tmp_path/'invalid.sqlite3')
    try:
        service = scheduler(manager, [100])
        with pytest.raises(ValueError):
            register(service, mode='execute', allowed_calls=[], model_budget=0)
        with pytest.raises(ValueError):
            register(service, mode='execute', allowed_calls=[{'name': 'unknown', 'arguments': {}}], model_budget=1)
    finally:
        manager.close()


def test_routine_cannot_enter_another_chat_or_manager(tmp_path):
    manager = TaskManager(db_path=tmp_path/'owner.sqlite3')
    service = scheduler(manager, [100])
    routine = register(service, mode='execute', allowed_calls=[{'name': 'obter_audio_windows', 'arguments': {}}], model_budget=1)
    service.authorize(routine['id'], chat_id='owner')
    calls = []
    wrong = SimpleNamespace(task_manager=manager, _garantir_sessao_chat=lambda: 'other',
        processar_mensagem=lambda *args, **kwargs: calls.append('nao chamar'),
        current_task=lambda: SimpleNamespace(state=TaskState.COMPLETED, task_id='fake'))
    try:
        with pytest.raises(RuntimeError):
            service.tick(wrong, chat_id='owner')
        assert calls == []
        assert service.get(routine['id'], chat_id='owner')['runs_left'] == 2
    finally:
        manager.close()


def test_authorized_read_runs_only_once_per_due_slot_and_honors_budget(tmp_path, monkeypatch):
    manager = TaskManager(db_path=tmp_path/'positive.sqlite3')
    clock = [100]
    service = scheduler(manager, clock)
    routine = register(service, mode='execute', allowed_calls=[{'name': 'obter_audio_windows', 'arguments': {}}], model_budget=1)
    service.authorize(routine['id'], chat_id='owner')
    effects = []
    item = SimpleNamespace(type='function_call', name='obter_audio_windows', arguments='{}', call_id='read')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name,
        lambda *_: effects.append('consulta ficticia') or ToolResult.success('Volume ficticio: 20'))
    pm = PermissionManager()
    h = AurenHarness(task_manager=manager, permission_manager=pm,
        criar_resposta=lambda *_: SimpleNamespace(output=[item], output_text='', usage=None),
        obter_chamadas=lambda r: r.output,
        executar_ferramenta=lambda call: dispatcher.executar_ferramenta(call, pm, None),
        mostrar_uso=lambda: None, comando_rapido=lambda _: (False, ''),
        iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None, fechar=lambda: None)
    from core.harness_runtime import SessionContext
    h._session = SessionContext('owner', tmp_path/'chat'/'chat.log')
    try:
        assert service.tick(h, chat_id='owner')[0]['kind'] == 'completed'
        assert service.tick(h, chat_id='owner') == []
        clock[0] = 160
        assert service.tick(h, chat_id='owner')[0]['kind'] == 'completed'
        assert effects == ['consulta ficticia'] * 2
        assert h.current_task().model_limit == h.current_task().model_calls == 1
        assert service.get(routine['id'], chat_id='owner')['status'] == 'exhausted'
    finally:
        h.shutdown()


def test_claim_write_failure_prevents_model_or_effect(tmp_path):
    import sqlite3
    manager = TaskManager(db_path=tmp_path/'claim.sqlite3')
    try:
        service = scheduler(manager, [100])
        routine = register(service)
        service.authorize(routine['id'], chat_id='owner')
        manager._storage.connection.execute("""CREATE TRIGGER refuse_claim BEFORE INSERT ON auren_routine_events
            WHEN NEW.operation='claim_before_effect' BEGIN SELECT RAISE(ABORT,'fixture'); END""")
        manager._storage.connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            service.tick(None, chat_id='owner')
        restored = service.get(routine['id'], chat_id='owner')
        assert restored['runs_left'] == 2 and restored['status'] == 'enabled'
    finally:
        manager.close()
