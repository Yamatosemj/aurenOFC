from types import SimpleNamespace as NS

import pytest

from scripts.diagnosticos.discovery_live_budget import DiscoveryBudget


def params():
    return dict(model=DiscoveryBudget.MODEL, input='synthetic fixture', reasoning={'effort':'none'},tools=[])


def response(**kw):
    return NS(status='completed',model=DiscoveryBudget.MODEL,usage=NS(input_tokens=100,output_tokens=20,
        input_tokens_details=NS(cached_tokens=10,cache_write_tokens=5),output_tokens_details=NS(reasoning_tokens=4)))


def test_shared_aggregate_reservation_blocks_before_fifty_cents(tmp_path):
    meter=DiscoveryBudget(tmp_path/'ledger.json');sent=[]
    def transport(**kw):
        assert meter.path.exists() and meter.data['calls'][-1]['status']=='reserved_usage_unknown'
        sent.append(kw);return response()
    for _ in range(13):meter.create(transport,**params())
    with pytest.raises(RuntimeError):meter.create(transport,**params())
    assert len(sent)==13 and meter.data['reserved_upper_usd']<.50
    assert all(p['service_tier']=='default' and p['store'] is False for p in sent)
    assert meter.data['calls'][0]['reasoning_tokens']==4
    assert meter.data['estimated_usd']>0
    with pytest.raises(FileExistsError):DiscoveryBudget(meter.path)


@pytest.mark.parametrize('failure',['timeout','missing','over_input','over_output'])
def test_unknown_or_inconsistent_usage_permanently_stops_spending(tmp_path,failure):
    meter=DiscoveryBudget(tmp_path/'ledger.json')
    def transport(**kw):
        if failure=='timeout':raise TimeoutError('secret must never be logged')
        r=response()
        if failure=='missing':r.usage=None
        if failure=='over_input':r.usage.input_tokens=999999
        if failure=='over_output':r.usage.output_tokens=999999
        return r
    with pytest.raises(RuntimeError):meter.create(transport,**params())
    with pytest.raises(RuntimeError):meter.create(lambda **k:pytest.fail('second request'),**params())
    assert len(meter.data['calls'])==1 and meter.data['reserved_upper_usd']>0
    assert 'secret' not in meter.path.read_text()


@pytest.mark.parametrize('extra',[{'model':'other'},{'previous_response_id':'x'},
    {'reasoning':{'effort':'low'}},{'input':'x'*60000},{'tools':[{'type':'web_search'}]},
    {'input':[{'type':'input_image'}]}])
def test_unbounded_or_additional_billable_services_never_reach_transport(tmp_path,extra):
    meter=DiscoveryBudget(tmp_path/'ledger.json');p=params();p.update(extra)
    with pytest.raises(RuntimeError):meter.create(lambda **k:pytest.fail('network'),**p)
    assert meter.data['calls']==[]
