"""New authorization, 2026-10-20: aggregate $0.50, no unknown-usage retries.

Only validated reported usage settles a reservation. Exposure uses deliberately
higher rates without cache discounts, leaving $0.01 untouched. Not an invoice.
All previous experiment ledgers remain separate and immutable.
"""
import json
from pathlib import Path
import time


class RoundBudget:
    AUTHORIZATION = 'user-session-2026-10-20-PR173-new-independent-round'
    MODEL = 'gpt-5.6-luna'
    LIMIT = .50
    STOP = .49
    RATES = dict(input=.20, cached=.02, cache_write=.25, output=1.20)

    def __init__(self, path, *, resume=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if resume:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            self._validate()
        else:
            self.data = dict(authorization=self.AUTHORIZATION, limit_usd=self.LIMIT,
                stop_before_usd=self.STOP, model=self.MODEL, rates_per_million=self.RATES,
                pricing_source='https://developers.openai.com/api/docs/models/gpt-5.6-luna',
                calls=[], estimated_usd=0., conservative_exposure_usd=0., billing_confirmed=False)
            with self.path.open('x', encoding='utf-8') as stream:
                json.dump(self.data, stream, indent=2)
        self.case = self.variant = self.phase = ''

    def _validate(self):
        d = self.data
        if (d.get('authorization') != self.AUTHORIZATION or d.get('limit_usd') != self.LIMIT
                or d.get('model') != self.MODEL or d.get('rates_per_million') != self.RATES
                or any(c.get('status') != 'received' for c in d.get('calls', []))):
            raise RuntimeError('Unknown usage or invalid authorization: stop spending')
        exposure = sum(c['settled_upper_usd'] for c in d['calls'])
        if exposure >= self.STOP or abs(exposure - d['conservative_exposure_usd']) > 1e-9:
            raise RuntimeError('Budget inconsistent or exhausted: stop spending')

    def save(self):
        tmp = self.path.with_suffix('.writing')
        tmp.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    def create(self, transport, **params):
        self._validate()
        if (params.get('model') != self.MODEL or params.get('previous_response_id')
                or params.get('reasoning') != {'effort': 'none'}
                or any(t.get('type') != 'function' for t in params.get('tools', []))):
            raise RuntimeError('Only bounded Luna text/function calls are authorized')
        cap = params.get('max_output_tokens', 600)
        if type(cap) is not int or cap <= 0:
            raise RuntimeError('Invalid output bound')
        params = dict(params, max_output_tokens=min(cap, 1200), service_tier='default', store=False)
        def serial(value):
            if hasattr(value, 'model_dump'):
                return value.model_dump(exclude_none=True)
            raise TypeError('Request must have a bounded wire representation')
        wire = json.dumps(params, ensure_ascii=False, default=serial).encode('utf-8')
        bound = len(wire) + 8192
        if bound > 60000 or any(x in wire for x in (b'input_image', b'input_audio')):
            raise RuntimeError('Request outside bounded text-only experiment')
        reserve = (bound * .60 + params['max_output_tokens'] * 3.) / 1e6
        exposure = self.data['conservative_exposure_usd']
        if exposure + reserve >= self.STOP:
            raise RuntimeError('Reserve would exceed stop line: no request sent')
        call = dict(number=len(self.data['calls'])+1, case=self.case, variant=self.variant,
            phase=self.phase, status='reserved_usage_unknown', model=self.MODEL,
            request_bytes=len(wire), input_bound=bound, output_cap=params['max_output_tokens'],
            reserve_usd=reserve, exposure_before_usd=exposure)
        self.data['calls'].append(call)
        self.data['conservative_exposure_usd'] = exposure + reserve
        self.save()  # durable before every principal/reviewer/auxiliary call
        start = time.perf_counter()
        try:
            response = transport(**params)
            usage = getattr(response, 'usage', None)
            inp, out = getattr(usage, 'input_tokens', None), getattr(usage, 'output_tokens', None)
            details = getattr(usage, 'input_tokens_details', None)
            cached = getattr(details, 'cached_tokens', 0) or 0
            written = getattr(details, 'cache_write_tokens', 0) or 0
            reasoning = getattr(getattr(usage, 'output_tokens_details', None), 'reasoning_tokens', 0) or 0
            if (any(type(n) is not int or n < 0 for n in (inp, out, cached, written, reasoning))
                    or not 0 < inp <= bound or out > params['max_output_tokens']
                    or cached + written > inp or reasoning > out
                    or getattr(response, 'model', None) != self.MODEL):
                raise RuntimeError('Usage or returned model inconsistent; no settlement')
            cost = ((inp-cached-written)*.20 + cached*.02 + written*.25 + out*1.20) / 1e6
            upper = (inp*.60 + out*3.) / 1e6
            call.update(status='received', response_status=getattr(response, 'status', 'unknown'),
                input_tokens=inp, output_tokens=out, cached_tokens=cached, cache_write_tokens=written,
                reasoning_tokens=reasoning, estimated_usd=cost, settled_upper_usd=upper,
                cache_neutral_usd=(inp*.25 + out*1.20)/1e6)
            self.data['conservative_exposure_usd'] = exposure + upper
            self.data['estimated_usd'] += cost
            return response
        except Exception as exc:
            call['error_type'] = type(exc).__name__
            raise RuntimeError('API failure or unknown usage; all further spending blocked') from None
        finally:
            call['latency_ms'] = round((time.perf_counter()-start)*1000, 3)
            self.save()
