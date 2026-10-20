from types import SimpleNamespace as NS
import pytest
from scripts.diagnosticos.discovery_round2_budget import RoundBudget


def params():
    return dict(model=RoundBudget.MODEL, input='synthetic', tools=[], reasoning={'effort':'none'})


def response():
    return NS(model=RoundBudget.MODEL, status='completed', usage=NS(input_tokens=100, output_tokens=20,
        input_tokens_details=NS(cached_tokens=10, cache_write_tokens=5),
        output_tokens_details=NS(reasoning_tokens=4)))


def test_reservation_precedes_transport_and_only_valid_usage_settles(tmp_path):
    meter=RoundBudget(tmp_path/'new-round.json')
    def transport(**kw):
        saved=__import__('json').loads(meter.path.read_text())
        assert saved['calls'][-1]['status']=='reserved_usage_unknown'
        assert saved['conservative_exposure_usd']<.49
        assert kw['service_tier']=='default' and not kw['store']
        return response()
    meter.create(transport,**params())
    c=meter.data['calls'][0]
    assert c['settled_upper_usd']<c['reserve_usd'] and c['reasoning_tokens']==4
    assert meter.data['estimated_usd']==pytest.approx((85*.2+10*.02+5*.25+20*1.2)/1e6)
    resumed=RoundBudget(meter.path,resume=True)
    assert resumed.data==meter.data
    with pytest.raises(FileExistsError):RoundBudget(meter.path)


def test_closed_round_cannot_be_spent_or_resumed(tmp_path):
    meter=RoundBudget(tmp_path/'ledger.json')
    meter.create(lambda **kw:response(),**params())
    meter.close()
    with pytest.raises(RuntimeError):meter.create(lambda **kw:pytest.fail('closed round'),**params())
    with pytest.raises(RuntimeError):RoundBudget(meter.path,resume=True)
    assert meter.data['closed'] and meter.data['max_pending_exposure_usd']<.49


@pytest.mark.parametrize('bad',['timeout','missing','model','bound','reasoning'])
def test_unknown_or_invalid_usage_stops_all_future_calls_and_resume(tmp_path,bad):
    m=RoundBudget(tmp_path/'ledger.json')
    def transport(**kw):
        if bad=='timeout':raise TimeoutError('secret')
        r=response()
        if bad=='missing':r.usage=None
        if bad=='model':r.model='other'
        if bad=='bound':r.usage.input_tokens=999999
        if bad=='reasoning':r.usage.output_tokens_details.reasoning_tokens=999
        return r
    with pytest.raises(RuntimeError):m.create(transport,**params())
    with pytest.raises(RuntimeError):m.create(lambda **k:pytest.fail('second request'),**params())
    with pytest.raises(RuntimeError):RoundBudget(m.path,resume=True)
    assert m.data['conservative_exposure_usd']>0 and 'secret' not in m.path.read_text()


def test_aggregate_bound_survives_many_settlements(tmp_path):
    m=RoundBudget(tmp_path/'ledger.json')
    # Near the ceiling with known expensive usage: the next call cannot send.
    while True:
        before=len(m.data['calls'])
        def expensive(**kw):
            r=response();r.usage.input_tokens=8000;r.usage.output_tokens=500;return r
        try:m.create(expensive,**params())
        except RuntimeError:
            assert len(m.data['calls'])==before
            break
    assert 0<m.data['estimated_usd']<=m.data['conservative_exposure_usd']<.49


@pytest.mark.parametrize('extra',[{'input':'x'*60000},{'model':'other'},
    {'reasoning':{'effort':'high'}},{'tools':[{'type':'web_search'}]},
    {'previous_response_id':'old'},{'input':[{'type':'input_image'}]}])
def test_invalid_requests_never_send(tmp_path,extra):
    m=RoundBudget(tmp_path/'ledger.json');p=params();p.update(extra)
    with pytest.raises(RuntimeError):m.create(lambda **k:pytest.fail('network'),**p)
    assert not m.data['calls']
