"""Ciclo real, SQLite e Dispatcher; modelo e efeitos pessoais ficticios."""
import json
from types import SimpleNamespace

import pytest

from agent.planner import PlanBuilder
from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from core.tool_result import ToolResult
from tools import dispatcher


@pytest.mark.parametrize('objective', [
    'Abra https://example.test/a.b?q=1.5 e depois consulte o volume.',
    'Digite "a; depois b. c" e depois consulte o volume.',
    r'Abra C:\fixture\relatorio.v2.exe e depois consulte o volume.',
    'Abra https://example.test/a;b?q=depois e depois consulte o volume.',
])
def test_plan_preserves_exact_data_and_only_splits_instruction_boundaries(objective):
    plan = PlanBuilder.build(objective)
    assert plan.objective == objective
    assert len(plan.steps) == 2
    assert plan.steps[0].instruction == objective.rsplit(' e depois ', 1)[0]


def call(name, args=None):
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args or {}), call_id=name)


def response(*calls, text=''):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


def harness(manager, pm, responses, *, verify=None, execute=None):
    return AurenHarness(task_manager=manager, permission_manager=pm,
        criar_resposta=lambda *_: responses.pop(0),
        executar_ferramenta=execute or (lambda item: dispatcher.executar_ferramenta(item, pm, None)),
        mostrar_uso=lambda: None, obter_chamadas=lambda r: r.output,
        comando_rapido=lambda _: (False, ''), iniciar_tarefa=pm.iniciar_tarefa,
        apos_tarefa=None, fechar=lambda: None, max_model_rounds=5,
        verificar_intencao=lambda *args: IntentDecision('aprovar', 'fixture'),
        verificar_conclusao=verify)


def test_pause_restart_continues_same_goal_without_repeating_first_effect(tmp_path, monkeypatch):
    db = tmp_path/'goals.sqlite3'
    effects = []
    manager = TaskManager(db_path=db)
    pm = PermissionManager()
    read = call('obter_audio_windows')
    write = call('definir_volume_windows', {'percentual': 35})
    h = harness(manager, pm, [response(read)])
    def first(*args):
        effects.append('read')
        h.pause_current_task()
        return ToolResult.success('Volume ficticio: 20')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, read.name, first)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, write.name,
        lambda *args: effects.append('write') or ToolResult.success('Volume ficticio: 35'))
    try:
        h.processar_mensagem('Consulte o volume e depois defina o volume para 35.')
        task = h.current_task()
        assert task.state is TaskState.PAUSED
        assert effects == ['read']
    finally:
        h.shutdown()
    manager = TaskManager(db_path=db)
    confirmations = []
    pm = PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request: confirmations.append(request) or False))
    h = harness(manager, pm, [response(write), response(text='feito')], verify=lambda *args: {})
    try:
        h.retomar_tarefa(task.task_id, chat_id=task.chat_id)
        assert h.current_task().task_id == task.task_id
        assert effects == ['read']  # Nova confirmacao foi negada.
        assert len(confirmations) == 1
        assert h.current_task().state is TaskState.FAILED
        assert h.current_task().model_calls > task.model_calls
    finally:
        h.shutdown()


def test_restored_permission_limits_keep_loop_budget_without_restoring_approval():
    pm = PermissionManager(max_actions=2)
    pm.actions_attempted = 2
    pm.same_successful_action_count = 3
    pm.last_successful_action_signature = pm._assinatura_acao('definir_volume_windows', {'percentual': 35})
    pm.last_authorized_action_signature = 'never restore approval'
    state = pm.checkpoint_limits()
    other = PermissionManager(max_actions=10)
    other.restore_limits(state)
    assert other.max_actions == 2 and other.actions_attempted == 2
    assert other.last_authorized_action_signature is None
    assert other.same_successful_action_count == 3
    assert other.fonte_nao_confiavel_pendente
    assert other.autorizar('definir_volume_windows', {'percentual': 36})[0] is False


@pytest.mark.parametrize('kind', ['missing_stage', 'bad_reference', 'command_only', 'pending'])
def test_incomplete_or_invented_evidence_cannot_approve_goal(tmp_path, kind):
    from core.task_verification import validate_completion
    manager = TaskManager(db_path=tmp_path/'evidence.sqlite3')
    try:
        manager.create('Defina o volume e depois consulte o volume.', plan=PlanBuilder.build(
            'Defina o volume e depois consulte o volume.'))
        manager.start()
        manager.begin_step('definir_volume_windows', '{"percentual":35}')
        manager.finish_step(success=True, result='Pedido recebido')
        manager.begin_step('obter_audio_windows')
        manager.finish_step(success=True, result='Volume ficticio:35')
        result = {'summary': 'fixture', 'steps': [
            {'index': 1, 'status': 'verified', 'evidence': [1, 2]},
            {'index': 2, 'status': 'verified', 'evidence': [2]}]}
        if kind == 'missing_stage':
            result['steps'].pop()
        elif kind == 'bad_reference':
            result['steps'][0]['evidence'] = [999]
        elif kind == 'command_only':
            result['steps'][0]['evidence'] = [1]
        else:
            result['steps'][1]['status'] = 'pending'
        with pytest.raises(RuntimeError):
            validate_completion(result, manager.current_snapshot())
    finally:
        manager.close()


def test_model_budget_is_reserved_before_call_and_survives_reopen(tmp_path):
    db = tmp_path/'budget.sqlite3'
    manager = TaskManager(db_path=db)
    task = manager.create('objetivo ficticio', chat_id='chat')
    manager.start()
    manager.configure_model_budget(1)
    manager.reserve_model_call()
    manager.close()
    manager = TaskManager(db_path=db)
    try:
        assert manager.get_snapshot(task.task_id).model_calls == 1
        with pytest.raises(RuntimeError):
            manager.configure_model_budget(10)
        with pytest.raises(RuntimeError):
            manager.reserve_model_call()
    finally:
        manager.close()


def test_compound_goal_cannot_finish_on_model_claim_without_verification(tmp_path, monkeypatch):
    manager = TaskManager(db_path=tmp_path/'verify.sqlite3')
    pm = PermissionManager()
    read = call('obter_audio_windows')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, read.name,
        lambda *args: ToolResult.success('Volume ficticio: 20'))
    h = harness(manager, pm, [response(read), response(text='Tudo concluido!')], verify=None)
    try:
        h.processar_mensagem('Consulte o volume e depois consulte o status do sistema.')
        assert h.current_task().state is TaskState.FAILED
        assert 'verific' in h.current_task().error
    finally:
        h.shutdown()


def test_wrong_chat_cannot_resume_even_safe_checkpoint(tmp_path):
    manager = TaskManager(db_path=tmp_path/'scope.sqlite3')
    task = manager.create('objetivo ficticio', chat_id='owner')
    manager.start()
    manager.pause()
    h = harness(manager, PermissionManager(), [])
    try:
        with pytest.raises(RuntimeError):
            h.retomar_tarefa(task.task_id, chat_id='other')
        assert manager.get_snapshot(task.task_id).state is TaskState.PAUSED
    finally:
        h.shutdown()


def test_successful_effect_cannot_be_replayed_after_restart(tmp_path, monkeypatch):
    db = tmp_path/'replay.sqlite3'
    effects = []
    pm = PermissionManager()
    manager = TaskManager(db_path=db)
    item = call('definir_volume_windows', {'percentual': 35})
    h = harness(manager, pm, [response(item)])
    def effect(*args):
        effects.append(35)
        h.pause_current_task()
        return ToolResult.success('Volume ficticio alterado')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name, effect)
    try:
        h.processar_mensagem('Defina o volume para 35 e depois consulte o volume.')
        task = h.current_task()
        assert task.state is TaskState.PAUSED
    finally:
        h.shutdown()
    manager = TaskManager(db_path=db)
    pm = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: True))
    h = harness(manager, pm, [response(item), response(text='feito')])
    try:
        h.retomar_tarefa(task.task_id, chat_id=task.chat_id)
        assert effects == [35]
        assert h.current_task().state is TaskState.FAILED
        assert h.current_task().error == 'resume_effect_repeated'
    finally:
        h.shutdown()


def test_resume_finishes_remaining_read_and_checks_actual_fixture_state(tmp_path, monkeypatch):
    db = tmp_path/'remaining.sqlite3'
    actual = {'volume': 0}
    item = call('definir_volume_windows', {'percentual': 35})
    read = call('obter_audio_windows')
    manager, pm = TaskManager(db_path=db), PermissionManager()
    h = harness(manager, pm, [response(item)])
    def effect(args, *_):
        actual['volume'] = args['percentual']
        h.pause_current_task()
        return ToolResult.success('Pedido enviado')
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name, effect)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, read.name,
        lambda *_: ToolResult.success(f"Volume ficticio: {actual['volume']}"))
    try:
        h.processar_mensagem('Defina o volume para 35 e depois consulte o volume.')
        task = h.current_task()
    finally:
        h.shutdown()

    reviews = []
    def verify(snapshot):
        reviews.append(snapshot)
        assert actual['volume'] == 35
        assert snapshot.steps[-1].result == 'Volume ficticio: 35'
        return {'summary': 'Estado ficticio conferido', 'steps': [
            {'index': 1, 'status': 'verified', 'evidence': [1, 2]},
            {'index': 2, 'status': 'verified', 'evidence': [2]}]}
    manager = TaskManager(db_path=db)
    h = harness(manager, PermissionManager(), [response(read), response(text='feito')], verify=verify)
    try:
        h.retomar_tarefa(task.task_id, chat_id=task.chat_id)
        assert h.current_task().state is TaskState.COMPLETED
        assert len(h.current_task().steps) == 2 and len(reviews) == 1
        assert h.current_task().model_calls > task.model_calls
    finally:
        h.shutdown()


def test_concurrent_message_cannot_reset_active_task_limits(tmp_path):
    import threading
    entered, release = threading.Event(), threading.Event()
    manager, pm = TaskManager(db_path=tmp_path/'concurrent.sqlite3'), PermissionManager()
    h = harness(manager, pm, [])
    errors = []
    def provider(*args):
        pm.actions_attempted = 2
        entered.set()
        assert release.wait(5)
        return response(text='resposta ficticia')
    h.criar_resposta = provider
    def first():
        try:
            h.processar_mensagem('oi')
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(RuntimeError):
            h.processar_mensagem('segunda mensagem')
        assert pm.actions_attempted == 2
    finally:
        release.set()
        thread.join(5)
        h.shutdown()
    assert not thread.is_alive() and errors == []


def test_completion_provider_has_no_tools_or_response_cache(tmp_path):
    from providers.openai_provider import OpenAIProvider
    from core.task_verification import FORMAT
    manager = TaskManager(db_path=tmp_path/'provider.sqlite3')
    captured = []
    provider = OpenAIProvider()
    def create(**kwargs):
        captured.append(kwargs)
        return response(text=json.dumps({'summary': 'faltam evidencias', 'steps': []}))
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    try:
        snapshot = manager.create('Consulte o volume e depois consulte o status.',
            plan=PlanBuilder.build('Consulte o volume e depois consulte o status.'))
        result = provider.verify_completion(snapshot)
        assert result['steps'] == []
        assert captured[0]['tools'] == [] and captured[0]['store'] is False
        assert captured[0]['text']['format'] == FORMAT
        assert json.loads(captured[0]['input'])['objective'] == snapshot.objective
    finally:
        manager.close()


def test_no_model_call_when_budget_reservation_cannot_be_saved(tmp_path, monkeypatch):
    import sqlite3
    manager, pm = TaskManager(db_path=tmp_path/'reserve.sqlite3'), PermissionManager()
    calls = []
    h = harness(manager, pm, [])
    h.criar_resposta = lambda *_: calls.append('provider') or response(text='nao executar')
    save = manager._storage.save
    def refuse(records, selected, operation, previous):
        if operation == 'reserve_model_call':
            raise sqlite3.OperationalError('reserva ficticia recusada')
        return save(records, selected, operation, previous)
    monkeypatch.setattr(manager._storage, 'save', refuse)
    try:
        h.processar_mensagem('oi')
        assert calls == []
        assert h.current_task().state is TaskState.FAILED
        assert h.current_task().model_calls == 0
    finally:
        h.shutdown()


def test_missing_final_stage_gets_one_bounded_recovery(tmp_path, monkeypatch):
    manager, pm = TaskManager(db_path=tmp_path/'recover.sqlite3'), PermissionManager()
    volume, status = call('obter_audio_windows'), call('obter_status_windows')
    seen = []
    for item in (volume, status):
        def handler(*args, name=item.name):
            seen.append(name)
            return ToolResult.success('Estado ficticio consultado: ' + name)
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS, item.name, handler)
    checks = []
    def verify(snapshot):
        checks.append(snapshot)
        complete = len(snapshot.steps) == 2
        return {'summary': 'falta consultar status' if not complete else 'leituras conferidas', 'steps': [
            {'index': 1, 'status': 'verified', 'evidence': [1]},
            {'index': 2, 'status': 'verified' if complete else 'pending', 'evidence': [2] if complete else []}]}
    h = harness(manager, pm, [response(volume), response(text='feito'),
        response(status), response(text='agora feito')], verify=verify)
    try:
        h.processar_mensagem('Consulte o volume e depois consulte o status do sistema.')
        assert seen == [volume.name, status.name]
        assert len(checks) == 2
        assert h.current_task().state is TaskState.COMPLETED
    finally:
        h.shutdown()
