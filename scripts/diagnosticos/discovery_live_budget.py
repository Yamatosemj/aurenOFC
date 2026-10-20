"""Opt-in PR #173 meter. Durable aggregate reserves never return to the pool."""
import json
from pathlib import Path
import time


class DiscoveryBudget:
    MODEL = 'gpt-5.6-luna'
    LIMIT = .50
    INPUT_BOUND = 60000
    RATES = {'input':.20, 'cached':.02, 'cache_write':.25, 'output':1.20}

    def __init__(self, path, *, resume=False):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data={'authorization':'PR173 issuecomment-6280094151', 'limit_usd':self.LIMIT,
            'source':'https://developers.openai.com/api/docs/pricing', 'rates_per_million':self.RATES,
            'reserved_upper_usd':0., 'estimated_usd':0., 'billing_confirmed':False, 'calls':[]}
        if resume:
            previous=json.loads(self.path.read_text(encoding='utf-8'))
            calls=previous.get('calls',[])
            if (previous.get('authorization')!=self.data['authorization']
                    or previous.get('limit_usd')!=self.LIMIT or previous.get('rates_per_million')!=self.RATES
                    or any(c.get('status')!='received' for c in calls)
                    or abs(sum(c['reserve_usd'] for c in calls)-previous['reserved_upper_usd'])>1e-9
                    or previous['reserved_upper_usd']>=self.LIMIT):
                raise RuntimeError('Ledger cannot resume safely')
            self.data=previous
            return
        # No silent restart or budget reset, even after a successful launch.
        with self.path.open('x',encoding='utf-8') as stream:json.dump(self.data,stream)
        self.case=self.phase=self.mode=''

    def save(self):
        tmp=self.path.with_suffix('.writing')
        tmp.write_text(json.dumps(self.data,indent=2),encoding='utf-8');tmp.replace(self.path)

    def create(self, transport, **params):
        if any(c['status']!='received' for c in self.data['calls']):
            raise RuntimeError('Unknown prior usage: no further spending')
        if (params.get('model')!=self.MODEL or params.get('previous_response_id')
                or params.get('reasoning')!={'effort':'none'}
                or any(t.get('type')!='function' for t in params.get('tools',[]))):
            raise RuntimeError('Request outside text/function-only authorization')
        params=dict(params,max_output_tokens=min(params.get('max_output_tokens',800),1200),
                    store=False,service_tier='default')
        if type(params['max_output_tokens']) is not int or params['max_output_tokens']<=0:
            raise RuntimeError('Invalid output ceiling')
        def serial(item):
            if hasattr(item,'model_dump'):return item.model_dump(exclude_none=True)
            if hasattr(item,'__dict__'):return vars(item)
            raise TypeError('Unbounded request object')
        raw=json.dumps(params,ensure_ascii=False,default=serial).encode('utf-8')
        bound=len(raw)+8192
        if bound>self.INPUT_BOUND or b'input_image' in raw or b'input_audio' in raw:
            raise RuntimeError('Request exceeds bounded text input')
        reserve=(self.INPUT_BOUND*.60+params['max_output_tokens']*3)/1e6
        if self.data['reserved_upper_usd']+reserve>=self.LIMIT:
            raise RuntimeError('Aggregate reserve exhausted: no request sent')
        call={'number':len(self.data['calls'])+1,'model':self.MODEL,'case':self.case,
            'phase':self.phase,'mode':self.mode,'status':'reserved_usage_unknown',
            'request_bytes':len(raw),'input_bound':bound,'output_cap':params['max_output_tokens'],
            'reserve_usd':reserve}
        self.data['calls'].append(call);self.data['reserved_upper_usd']+=reserve
        self.save() # before transport, including reviewers and all auxiliary calls
        started=time.perf_counter()
        try:
            response=transport(**params)
            usage=getattr(response,'usage',None)
            inp,out=getattr(usage,'input_tokens',None),getattr(usage,'output_tokens',None)
            details=getattr(usage,'input_tokens_details',None)
            cached=getattr(details,'cached_tokens',0) or 0
            written=getattr(details,'cache_write_tokens',0) or 0
            reasoning=getattr(getattr(usage,'output_tokens_details',None),'reasoning_tokens',0) or 0
            if (any(type(v) is not int or v<0 for v in (inp,out,cached,written,reasoning))
                    or inp>bound or inp<=0 or out>params['max_output_tokens']
                    or cached+written>inp or reasoning>out):
                raise RuntimeError('Missing or inconsistent usage: stop spending')
            cost=((inp-cached-written)*.20+cached*.02+written*.25+out*1.20)/1e6
            call.update(status='received',response_status=getattr(response,'status','unknown'),
                returned_model=getattr(response,'model',None),input_tokens=inp,output_tokens=out,
                cached_tokens=cached,cache_write_tokens=written,reasoning_tokens=reasoning,estimated_usd=cost)
            self.data['estimated_usd']+=cost
            return response
        except Exception as exc:
            call['error_type']=type(exc).__name__
            raise RuntimeError('Live call failed; reserve retained and further calls blocked') from None
        finally:
            call['latency_ms']=round((time.perf_counter()-started)*1000,3)
            self.save()
