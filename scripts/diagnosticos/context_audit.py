"""Offline ONLY: capture real provider payloads using scripted model responses.

No real OpenAI client is constructed. All Dispatcher handlers are replaced.
Run with offline_python.py and an isolated tiktoken 0.12.0 / cached o200k_base.
Token counts are component-level proxies, never provider usage or invoices.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS
from unittest.mock import patch

SCRIPT = Path(__file__).resolve()
FLAGS = {"reviews": "AUREN_CONTEXT_COMPACT_REVIEWS", "plan": "AUREN_CONTEXT_COMPACT_PLAN"}


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "__dict__"):
        return plain(vars(value))
    return value


def text(value):
    return value if isinstance(value, str) else json.dumps(plain(value), ensure_ascii=False, separators=(",", ":"))


def worker(args):
    sys.path.insert(0, str(Path.cwd()))
    import tiktoken
    from core.harness import AurenHarness
    from core.orchestrator import AurenOrchestrator
    from core.permission_manager import PermissionManager
    from core.task_manager import TaskManager
    from core.task_trace import TaskTraceStore
    from core.session import SessionContextManager
    from core.tool_result import ToolResult
    from core import harness_runtime as runtime
    from core.intent_verification import INSTRUCTIONS as INTENT
    from core.task_verification import INSTRUCTIONS as COMPLETION
    from providers.openai_provider import OpenAIProvider
    from tools import dispatcher
    from memory.store import PersistentMemoryStore
    enc = tiktoken.get_encoding("o200k_base")
    count = lambda value: len(enc.encode(text(value), disallowed_special=()))
    case = next(c for c in json.loads(args.cases.read_text(encoding="utf-8")) if c["id"] == args.case)
    requests, executed, decisions, turns, context_builds = [], [], [], [], []
    responses, candidate = [], [""]
    world = {"volume": 42, "mute": False, "active": 1}
    pending_snapshot = [None]
    previous_prefix = {"principal": "", "intent": "", "completion": ""}

    def audio(_args, *_):
        return ToolResult.success(f'Volume master: {world["volume"]}%\nMudo: '+('ativado' if world['mute'] else 'desativado'))

    def volume(data, *_):
        world['volume'] = data['percentual']
        return ToolResult.success(f'Volume definido para {world["volume"]}%.')

    def mute(data, *_):
        world['mute'] = data['ativado']
        return ToolResult.success('Estado de mudo atualizado.')

    def tabs(*_):
        return ToolResult.success('Abas abertas: 2\nAba ativa: '+str(world['active'])+
            '\nAba 1: Guia Alfa | https://example.invalid/alfa\nAba 2: Guia Beta | https://example.invalid/beta')

    def switch(data, *_):
        world['active'] = data['indice']
        return ToolResult.success('Aba alterada.')

    def page(*_):
        code = 'BETA-82' if world['active'] == 2 else 'ALFA-27'
        return ToolResult.success('Codigo: '+code, data={'pagina': {'codigo': code}}, conteudo_nao_confiavel=True)

    handlers = {name: (lambda *_: ToolResult.failure('No synthetic handler', error_code='fixture_denied'))
                for name in dispatcher.TOOL_HANDLERS}
    handlers.update(obter_audio_windows=audio, definir_volume_windows=volume, definir_mudo_windows=mute,
        listar_abas=tabs, trocar_aba=switch, ler_pagina=page,
        listar_janelas_windows=lambda *_: ToolResult.success('Janelas encontradas: 2\n1. Relatorio Sintetico\n2. Editor Sintetico'))

    def fake_create(**kw):
        phase = 'intent' if kw['instructions'] == INTENT else ('completion' if kw['instructions'] == COMPLETION else 'principal')
        components = {'instructions': kw['instructions'], 'schemas': kw.get('tools', []),
                      'response_format': kw.get('text', {})}
        inp = plain(kw['input'])
        if isinstance(inp, str):
            components['state_or_review'] = inp
        else:
            grouped = {}
            for item in inp:
                kind = item.get('type', 'message')
                grouped.setdefault(kind, []).append(item)
            components.update(grouped)
        # Empty arrays/objects have no model content in these accounting proxies.
        sizes = {k: {'chars': len(text(v)), 'tokens_proxy': count(v)}
                 for k, v in components.items() if v not in ([], {}, '')}
        prefix = text([kw['instructions'], kw.get('tools', []), kw.get('text', {})])
        old = previous_prefix[phase]
        shared = os.path.commonprefix([old, prefix]) if old else ''
        previous_prefix[phase] = prefix
        if phase == 'intent':
            decision = {'decisao': args.intent, 'motivo': 'Decisao sintetica, sem autorizacao de execucao.', 'pergunta': ''}
            decisions.append(decision)
            reply = NS(output=[], output_text=json.dumps(decision), usage=None)
        elif phase == 'completion':
            snap = pending_snapshot[0]
            review = {'summary': 'Synthetic review only', 'answer_status': 'verified',
                'steps': [{'index': s.index, 'status': 'verified',
                    'evidence': [i for i, step in enumerate(snap.steps, 1) if step.success is True]}
                    for s in snap.plan.steps]}
            reply = NS(output=[], output_text=json.dumps(review), usage=None)
        else:
            if responses:
                batch = responses.pop(0)
                calls = [NS(type='function_call', name=name, arguments=json.dumps(parameters, ensure_ascii=False),
                            call_id=f'c{len(requests)}-{i}') for i, (name, parameters) in enumerate(batch)]
                reply = NS(output=calls, output_text='', usage=None)
            else:
                reply = NS(output=[], output_text=candidate[0], usage=None)
        requests.append({'phase': phase, 'components': sizes, 'input_tokens_proxy': sum(v['tokens_proxy'] for v in sizes.values()),
            'output_tokens_proxy': count(reply.output_text) + (count(reply.output) if reply.output else 0),
            'stable_prefix_chars': len(prefix), 'same_phase_shared_prefix_chars': len(shared),
            'instructions_sha256': hashlib.sha256(kw['instructions'].encode()).hexdigest(),
            'schemas_sha256': hashlib.sha256(text(kw.get('tools', [])).encode()).hexdigest(),
            'previous_response_id': kw.get('previous_response_id'),
            'cache_options': kw.get('prompt_cache_options'),
            'actual_input_tokens': None, 'actual_cached_tokens': None, 'actual_cache_write_tokens': None,
            'actual_api_latency_ms': None, 'actual_estimated_usd': None})
        if phase == 'principal':
            context = h._contexto_tarefa
            state = inp if isinstance(inp,str) else inp[0]['content'][0]['text']
            requests[-1]['retrieved_context_chars'] = len(context)
            requests[-1]['retrieved_context_present'] = bool(context) and context in state
            requests[-1]['state_chars'] = len(state)
        return reply

    provider = OpenAIProvider()
    provider._client = NS(responses=NS(create=fake_create))
    orchestrator = AurenOrchestrator(provider=provider)
    def model(entrada, response_id=None, reasoning_effort='none', tool_choice=None):
        return orchestrator.create_response(entrada, response_id=response_id,
            reasoning_effort=reasoning_effort, tool_choice=tool_choice)
    manager = PermissionManager(confirmation_channel=NS(confirmar=lambda _: args.permission == 'allow'))
    allowed = {name for turn in case['turns'] for batch in turn['rounds'] for name, _ in batch}

    def execute(item):
        result = dispatcher.executar_ferramenta(item, manager, None)
        executed.append({'tool': item.name, 'arguments': json.loads(item.arguments), 'ok': result.ok,
                         'error': result.error_code})
        return result

    def completion(snapshot):
        pending_snapshot[0] = snapshot
        return provider.verify_completion(snapshot)

    def start():
        manager.iniciar_tarefa()
        if args.permission == 'deny':
            manager.registrar_fonte_nao_confiavel('synthetic-confirmation-test')

    with tempfile.TemporaryDirectory(prefix='context-audit-') as tmp, ExitStack() as stack:
        folder = Path(tmp)
        for name, val in {'LOG_DIR': folder/'logs', 'CHAT_LOGS_DIR': folder/'chats',
                          'TASK_LOG_DIR': folder/'tasks', 'LOG_FILE': folder/'logs'/'auren.log'}.items():
            stack.enter_context(patch.object(runtime, name, val))
        stack.enter_context(patch.dict(dispatcher.TOOL_HANDLERS, handlers, clear=True))
        tm = TaskManager(db_path=folder/'tasks.sqlite3')
        store = PersistentMemoryStore(folder/'memory.sqlite3')
        context = SessionContextManager(store)
        original_build = context.build
        def build(*v, **kw):
            snap = original_build(*v, **kw)
            context_builds.append({'sections': {name: {'chars': len(value), 'tokens_proxy': count(value)}
                                   for name,value in snap.secoes}, 'chars':len(snap.texto)})
            return snap
        context.build = build
        h = AurenHarness(criar_resposta=model, executar_ferramenta=execute,
            verificar_intencao=provider.verify_intent, verificar_conclusao=completion,
            permission_manager=manager, task_manager=tm,
            context=context, trace_store=TaskTraceStore(folder/'trace.sqlite3'),
            mostrar_uso=lambda: None, obter_chamadas=lambda r: r.output,
            comando_rapido=lambda _:(False,''), iniciar_tarefa=start,
            registrar_fonte_nao_confiavel=manager.registrar_fonte_nao_confiavel,
            apos_tarefa=None, fechar=lambda: None, max_model_rounds=8)
        started = time.perf_counter()
        try:
            for turn in case['turns']:
                responses[:] = list(turn['rounds'])
                candidate[0] = turn['answer']
                first_request, first_effect = len(requests), len(executed)
                _, answer = h.processar_mensagem(turn['prompt'], execution_scope=lambda item: item.name in allowed,
                                                model_budget=24)
                snap = h.current_task()
                answer_text = str(getattr(answer, 'output_text', ''))
                expected = [{'tool':name,'arguments':parameters} for batch in turn['rounds'] for name,parameters in batch]
                observed = [{'tool':item['tool'],'arguments':item['arguments']} for item in executed[first_effect:] if item['ok']]
                turns.append({'state': snap.state.value, 'error': snap.error,
                    'answer_matches': answer_text == turn['answer'],
                    'facts_ok': all(f in answer_text for f in turn.get('facts',[turn['answer']])),
                    'actions_match': observed == expected,
                    'request_indices': list(range(first_request, len(requests))),
                    'executed': executed[first_effect:]})
                # Make post-task memory availability identical across variants.
                h._background_queue._queue.join()
            duration = (time.perf_counter()-started)*1000
        finally:
            h.shutdown()
            if not tm.closed:
                tm.close()
    result = {'case': case['id'], 'split': case['split'], 'variant': args.variant,
        'intent_fixture': args.intent, 'permission_fixture': args.permission,
        'source_sha': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        'dirty': bool(subprocess.check_output(['git','status','--porcelain'], text=True).strip()),
        'scripted_success': all(t['state']=='completed' and t['facts_ok'] and t['actions_match'] for t in turns),
        'calls_to_fake_transport': len(requests), 'phases': dict(Counter(r['phase'] for r in requests)),
        'input_tokens_proxy': sum(r['input_tokens_proxy'] for r in requests),
        'output_tokens_proxy': sum(r['output_tokens_proxy'] for r in requests),
        'offline_duration_ms': round(duration,3), 'turns': turns, 'requests': requests, 'context_builds':context_builds,
        'real_api_calls': 0, 'real_terminal_effects': 0, 'paid_usd': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cases', type=Path, default=SCRIPT.with_name('context_audit_cases.json'))
    p.add_argument('--case')
    p.add_argument('--worker', action='store_true')
    p.add_argument('--variant', default='base')
    p.add_argument('--intent', choices=['aprovar','bloquear'], default='aprovar')
    p.add_argument('--permission', choices=['allow','deny'], default='allow')
    args = p.parse_args()
    if os.getenv('AUREN_TEST_MODE') != '1':
        p.error('Use offline_python.py; this runner has no Live mode')
    args.output = args.output.resolve()
    args.cases = args.cases.resolve()
    if args.worker:
        return worker(args)
    if not args.base:
        p.error('--base checkout required')
    results = []
    variants = [('base', args.base), ('reviews', SCRIPT.parents[2]),
                ('plan', SCRIPT.parents[2]), ('combined', SCRIPT.parents[2])]
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    for case in cases:
        for variant, root in variants:
            env = dict(os.environ)
            for name, flag in FLAGS.items():
                env[flag] = '1' if variant in (name,'combined') else '0'
            output = args.output / f'{case["id"]}-{variant}.json'
            subprocess.run([sys.executable, str(SCRIPT), '--worker', '--case', case['id'],
                '--variant', variant, '--cases', str(args.cases), '--output', str(output),
                '--intent', args.intent, '--permission', args.permission], cwd=root, env=env, check=True, timeout=60)
            results.append(json.loads(output.read_text(encoding='utf-8')))
    summary = {'base_sha': '48717bb68fd3545d31aa33028261fa33f9f50177',
        'cases_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        'method': 'scripted responses, real Harness/Router/Dispatcher/contracts/PM/provider serializers; o200k_base component proxy',
        'provider_usage': None, 'paid_usd': 0, 'variants': {}}
    for variant, _ in variants:
        group = [r for r in results if r['variant']==variant]
        summary['variants'][variant] = {'trials': len(group), 'scripted_success': sum(r['scripted_success'] for r in group),
            'fake_calls': sum(r['calls_to_fake_transport'] for r in group),
            'input_tokens_proxy': sum(r['input_tokens_proxy'] for r in group),
            'output_tokens_proxy': sum(r['output_tokens_proxy'] for r in group)}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
