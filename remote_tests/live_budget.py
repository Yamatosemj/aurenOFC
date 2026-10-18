"""Explicit Live-only transport guard. Never imported by production runtime."""
import json
from pathlib import Path
from threading import Lock


class LiveBudget:
    MODEL = 'gpt-5.6-luna'
    MAX_CALLS = 8
    MAX_USD = .50
    MAX_INPUT_BOUND = 60000

    def __init__(self, path, *, resume=False):
        self.path = Path(path)
        self.lock = Lock()
        self.data = {'model': self.MODEL, 'max_calls': self.MAX_CALLS, 'max_usd': self.MAX_USD,
            'calls': [], 'estimated_usd': 0.0, 'reserved_upper_usd': 0.0,
            'billing_confirmed': False,
            'rates_per_million': {'input': .20, 'cached': .02, 'cache_write': .25, 'output': 1.20},
            'source': 'https://developers.openai.com/api/docs/pricing'}
        if resume:
            existing = json.loads(self.path.read_text(encoding='utf-8'))
            if (any(existing.get(k) != self.data[k] for k in ('model','max_calls','max_usd','rates_per_million'))
                    or not isinstance(existing.get('calls'), list)
                    or len(existing['calls']) > self.MAX_CALLS
                    or any(c.get('status') != 'received' for c in existing['calls'])
                    or abs(sum(c['upper_usd'] for c in existing['calls'])-existing['reserved_upper_usd']) > 1e-9
                    or existing['reserved_upper_usd'] > self.MAX_USD):
                raise RuntimeError('Existing Live authorization cannot be resumed safely')
            self.data = existing
            return
        # One authorization ledger per cycle. A second launch cannot reset it.
        with self.path.open('x', encoding='utf-8') as stream:
            json.dump(self.data, stream, indent=2)

    def _save(self):
        temporary = self.path.with_suffix('.writing')
        temporary.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def create(self, transport, **params):
        with self.lock:
            if params.get('model') != self.MODEL:
                raise RuntimeError('Live budget refuses another model')
            params = dict(params, max_output_tokens=min(params.get('max_output_tokens', 800), 1200), store=False)
            # UTF-8 bytes overestimate text token count; reserve extra framing
            # margin for instructions, tool schemas and structured output.
            bound = len(json.dumps(params, ensure_ascii=False, default=str).encode('utf-8')) + 4096
            if bound > self.MAX_INPUT_BOUND:
                raise RuntimeError('Live input exceeds conservative token bound')
            # Above standard rates, including cache writes, long-context and
            # regional surcharge. Keep reservations even after known success.
            ceiling = (self.MAX_INPUT_BOUND * .60 + params['max_output_tokens'] * 3.00) / 1_000_000
            if (len(self.data['calls']) >= self.MAX_CALLS
                    or self.data['reserved_upper_usd'] + ceiling > self.MAX_USD):
                raise RuntimeError('Live authorization limit reached; no request sent')
            call = {'number': len(self.data['calls']) + 1, 'status': 'reserved_before_request',
                'input_token_bound': bound, 'max_output_tokens': params['max_output_tokens'],
                'upper_usd': ceiling, 'kind': params.get('text', {}).get('format', {}).get('name', 'response')}
            self.data['calls'].append(call)
            self.data['reserved_upper_usd'] += ceiling
            self._save()
            try:
                response = transport(**params)
            except Exception as exc:
                call.update(status='failed_usage_unknown', error_type=type(exc).__name__)
                self._save()
                raise RuntimeError('Live request failed; usage unknown, no automatic retry') from None
            from core.usage import extrair_metricas_uso
            metrics = extrair_metricas_uso(response)
            if not metrics:
                call['status'] = 'response_usage_unknown'
                self._save()
                raise RuntimeError('Live response missing usage; stopping')
            rates = self.data['rates_per_million']
            regular = max(0, metrics['input_tokens']-metrics['cached_tokens']-metrics['cache_write_tokens'])
            cost = (regular*rates['input'] + metrics['cached_tokens']*rates['cached']
                + metrics['cache_write_tokens']*rates['cache_write'] + metrics['output_tokens']*rates['output'])/1_000_000
            call.update(status='received', tokens=metrics, estimated_usd=cost)
            self.data['estimated_usd'] += cost
            self._save()
            return response
