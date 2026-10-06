
import pytest
from core.task_manager import TaskManager, TaskState


def _running():
    manager = TaskManager()
    snap = manager.create("objetivo", chat_id="chat")
    manager.start(snap.task_id)
    return manager, snap.task_id


def test_cancel_requested_then_complete_becomes_cancelled():
    manager, task_id = _running()
    manager.begin_step("fake", "{}", task_id=task_id)
    manager.finish_step(success=True, result="ok", task_id=task_id)
    manager.request_cancel(task_id)
    snapshot = manager.complete("late success", task_id=task_id)
    assert snapshot.state is TaskState.CANCELLED
    assert snapshot.result == ""
    assert snapshot.cancel_requested is True


def test_terminal_state_rejects_mutation_operations():
    manager, task_id = _running()
    manager.complete("ok", task_id=task_id)
    before = manager.current_snapshot()
    with pytest.raises(RuntimeError):
        manager.request_cancel(task_id)
    with pytest.raises(RuntimeError):
        manager.cancel(task_id=task_id)
    with pytest.raises(RuntimeError):
        manager.fail("late", task_id=task_id)
    after = manager.current_snapshot()
    assert after == before


def test_failed_state_rejects_late_complete_and_preserves_error():
    manager, task_id = _running()
    manager.fail("original", task_id=task_id)
    before = manager.current_snapshot()
    with pytest.raises(RuntimeError):
        manager.complete("late", task_id=task_id)
    assert manager.current_snapshot() == before


def test_cancelled_state_rejects_late_complete():
    manager, task_id = _running()
    manager.cancel(task_id=task_id, reason="user")
    before = manager.current_snapshot()
    with pytest.raises(RuntimeError):
        manager.complete("late", task_id=task_id)
    assert manager.current_snapshot() == before
