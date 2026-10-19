from types import SimpleNamespace
import pytest
from tests.live_latency_api import LiveBudget


def params():
    return {'model':'gpt-5.6-luna','reasoning':{'effort':'none'},'input':'fixture','tools':[]}


def test_budget_reservation_survives_error_and_restart(tmp_path):
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs)
        raise TimeoutError('synthetic')
    path=tmp_path/'budget.json'
    budget=LiveBudget(path,fail)
    with pytest.raises(TimeoutError):budget.create(**params())
    after=LiveBudget(path,fail)
    assert len(calls)==1 and len(after.data['calls'])==1
    assert after.data['reserved_usd']>0
    assert calls[0]['max_output_tokens']==1200 and calls[0]['service_tier']=='default'


def test_budget_refuses_before_network_and_never_refunds(tmp_path):
    budget=LiveBudget(tmp_path/'budget.json',lambda **_:pytest.fail('Over budget network call'))
    budget.data['reserved_usd']=0.499
    with pytest.raises(RuntimeError,match='reserve exhausted'):budget.create(**params())
    assert budget.data['reserved_usd']==0.499 and budget.data['calls']==[]


@pytest.mark.parametrize('extra',[{'model':'other'},{'previous_response_id':'previous'},
    {'input':'x'*48001},{'tools':[{'type':'web_search'}]}, {'input':[{'type':'input_image'}]}])
def test_unbounded_requests_cannot_reach_network(tmp_path,extra):
    budget=LiveBudget(tmp_path/'budget.json',lambda **_:pytest.fail('Unexpected network call'))
    p=params();p.update(extra)
    with pytest.raises(RuntimeError):budget.create(**p)
    assert budget.data['calls']==[]
