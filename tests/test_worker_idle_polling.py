"""Scheduler polling is not user activity; only actual work emits busy/idle."""
from types import SimpleNamespace

import pytest

from ui.backend import AurenUiWorker, ConfirmationChoice, UiEvent
from ui.chrome_server import LocalChromeApp


def app_with_scheduler(monkeypatch, state='completed', *, due=False, fail=False):
    clock = [1000.0]
    monkeypatch.setattr('ui.chrome_server.monotonic', lambda: clock[0])
    worker = AurenUiWorker(task_db_path=False)
    monkeypatch.setattr(worker, 'start', lambda: None)
    worker._harness = SimpleNamespace(
        current_task=lambda: SimpleNamespace(state=SimpleNamespace(value=state)),
        _session=SimpleNamespace(chat_id='discardable'),
    )
    ticks = []

    def tick(_harness, *, chat_id):
        ticks.append(chat_id)
        if fail:
            raise RuntimeError('simulated scheduler failure')
        return [{'text': 'simulated work', 'kind': 'completed'}]

    worker._scheduler = SimpleNamespace(
        manager=SimpleNamespace(closed=False),
        list=lambda **_: [{'status': 'enabled', 'next_due': 0}] if due else [],
        tick=tick,
    )
    app = LocalChromeApp(worker)
    app.change_mode('active')
    return app, worker, clock, ticks


def test_no_due_routines_do_not_renew_activity_or_prevent_standby(monkeypatch):
    app, worker, clock, ticks = app_with_scheduler(monkeypatch)
    for second in (1, 30, 60, 119, 120):
        clock[0] = 1000.0 + second
        worker._poll_routines()
        snapshot = app.snapshot()
        assert app.last_activity == 1000.0
        assert snapshot['mode'] == ('standby' if second == 120 else 'active')
    assert not ticks
    assert snapshot['events'] == []


def test_poll_during_unfinished_task_never_clears_busy(monkeypatch):
    app, worker, clock, ticks = app_with_scheduler(monkeypatch, state='waiting')
    app.busy = True
    clock[0] += 300
    worker._poll_routines()
    snapshot = app.snapshot()
    assert snapshot['busy'] is True
    assert snapshot['mode'] == 'active'
    assert snapshot['events'] == []
    assert not ticks


def test_pending_confirmation_prevents_standby_without_fake_activity(monkeypatch):
    app, worker, clock, ticks = app_with_scheduler(monkeypatch)
    choice = ConfirmationChoice('Simulated action', 'No executor', 'fixture')
    worker.events.put(UiEvent('confirm', payload=choice, generation=worker.generation))
    app.snapshot()
    clock[0] += 300
    worker._poll_routines()
    assert app.snapshot()['mode'] == 'active'
    assert app.last_activity == 1000.0
    assert not choice.decided.is_set()
    request_id = app.pending[0]
    app.confirm(request_id, False)
    assert choice.decided.is_set() and not choice.approved
    assert app.snapshot()['mode'] == 'standby'
    assert not ticks


@pytest.mark.parametrize('fail', [False, True])
def test_actual_scheduler_work_keeps_balanced_busy_and_idle(monkeypatch, fail):
    app, worker, clock, ticks = app_with_scheduler(monkeypatch, due=True, fail=fail)
    clock[0] += 30
    worker._poll_routines()
    snapshot = app.snapshot()
    assert [event['kind'] for event in snapshot['events']] == ['busy', 'notice', 'idle']
    assert snapshot['busy'] is False
    assert snapshot['mode'] == 'active'
    assert app.last_activity == clock[0]
    assert ticks == ['discardable']
