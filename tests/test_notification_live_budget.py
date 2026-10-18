"""Budget guards with fake transports; these tests never call the API."""
from types import SimpleNamespace

import pytest

from remote_tests.live_budget import LiveBudget


def test_guard_counts_all_requests_and_refuses_ninth(tmp_path):
    budget = LiveBudget(tmp_path/'budget.json')
    seen = []
    def fake(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(model=budget.MODEL, usage=SimpleNamespace(
            input_tokens=100, output_tokens=20, input_tokens_details=None))
    for _ in range(8):
        budget.create(fake, model=budget.MODEL, input='fictitious')
    with pytest.raises(RuntimeError):
        budget.create(fake, model=budget.MODEL, input='fictitious')
    assert len(seen) == 8 and all(x['store'] is False for x in seen)
    assert budget.data['reserved_upper_usd'] < .5
    assert budget.data['estimated_usd'] > 0
    with pytest.raises(FileExistsError):
        LiveBudget(budget.path)


def test_failure_keeps_reservation_and_is_not_retried(tmp_path):
    budget = LiveBudget(tmp_path/'budget.json')
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise TimeoutError('fictitious')
    with pytest.raises(RuntimeError):
        budget.create(fail, model=budget.MODEL, input='fictitious')
    assert len(calls) == len(budget.data['calls']) == 1
    assert budget.data['calls'][0]['status'] == 'failed_usage_unknown'
    assert budget.data['reserved_upper_usd'] > 0


@pytest.mark.parametrize('params', [
    {'model':'another-model', 'input':'fictitious'},
    {'model':LiveBudget.MODEL, 'input':'x'*60000},
])
def test_invalid_request_stops_before_transport(tmp_path, params):
    budget = LiveBudget(tmp_path/'budget.json')
    with pytest.raises(RuntimeError):
        budget.create(lambda **k: pytest.fail('must not send'), **params)
    assert not budget.data['calls']


def test_explicit_continuation_preserves_spending_and_the_eight_call_limit(tmp_path):
    first = LiveBudget(tmp_path/'budget.json')
    def fake(**kwargs):
        return SimpleNamespace(model=first.MODEL, usage=SimpleNamespace(
            input_tokens=100, output_tokens=20, input_tokens_details=None))
    for _ in range(5):
        first.create(fake, model=first.MODEL, input='fictitious')
    spent = first.data['estimated_usd']
    resumed = LiveBudget(first.path, resume=True)
    assert resumed.data['estimated_usd'] == spent and len(resumed.data['calls']) == 5
    for _ in range(3):
        resumed.create(fake, model=first.MODEL, input='new fictitious case')
    with pytest.raises(RuntimeError):
        resumed.create(lambda **k:pytest.fail('ninth call'), model=first.MODEL, input='fictitious')
    assert resumed.data['estimated_usd'] > spent
