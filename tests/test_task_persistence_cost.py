"""Persistence cost must depend on changed records, preserving rollback."""
import pytest
from core.task_manager import TaskManager, TaskState
import core.task_manager as module


def populated(path, count=20):
    manager = TaskManager(db_path=path, max_history=5)
    for n in range(count):
        manager.create('fixture ' + str(n), chat_id='fixture', task_id='task-'+str(n))
        manager.start()
        manager.complete('done')
    return manager


def test_transition_serializes_only_selected_record(tmp_path, monkeypatch):
    manager = populated(tmp_path/'tasks.sqlite3')
    manager.create('active', task_id='active', chat_id='fixture')
    manager.start()
    seen = []
    original = module.asdict
    def capture(value):
        seen.append(value.task_id)
        return original(value)
    monkeypatch.setattr(module, 'asdict', capture)
    try:
        manager.wait_for_model()
        assert set(seen) == {'active'} and len(seen) == 2
        assert len(manager.list_snapshots('fixture')) == 21  # archived tasks survive pruning
    finally:
        manager.close()


@pytest.mark.parametrize('operation', ['step', 'budget', 'create', 'clear'])
def test_persistence_failure_restores_records_and_selection(tmp_path, monkeypatch, operation):
    path = tmp_path/'tasks.sqlite3'
    manager = populated(path)
    if operation in {'step', 'budget'}:
        manager.create('active', chat_id='fixture')
        manager.start()
    before = manager.current_snapshot()
    records_before = manager._records()
    def fail(*args):
        raise OSError('synthetic disk failure')
    with monkeypatch.context() as patch:
        patch.setattr(manager._storage, 'save', fail)
        with pytest.raises(OSError):
            if operation == 'step':
                manager.begin_step('abrir_programa', '{}')
            elif operation == 'budget':
                manager.configure_model_budget(10)
            elif operation == 'create':
                manager.create('new task')
            else:
                manager.clear_current()
    assert manager.current_snapshot() == before
    assert manager._records() == records_before
    manager.close()
    recovered = TaskManager(db_path=path)
    try:
        task = recovered.current_snapshot()
        assert task.task_id == before.task_id
        assert task.steps == before.steps and task.model_calls == before.model_calls
        assert task.state in {TaskState.COMPLETED, TaskState.INTERRUPTED}
    finally:
        recovered.close()
