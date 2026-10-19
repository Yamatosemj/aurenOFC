"""Explicit live probe: real provider + normal Harness/Router/Dispatcher.

No API call on import. --run is mandatory. One scenario per process; persistent
budget reserves are never refunded, including failed or unknown-usage calls.
Only synthetic windows and public YouTube recipe navigation are in scope.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class LiveBudget:
    LIMIT = 0.50

    def __init__(self, path, create):
        self.path, self.create_api = Path(path), create
        self.case, self.phase = '', ''
        self.source_commit = ''
        self.data = (json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists()
                     else {'limit_usd':self.LIMIT, 'reserved_usd':0, 'estimated_usd':0, 'calls':[]})
        if self.data['limit_usd'] != self.LIMIT:
            raise RuntimeError('Unexpected existing budget')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def create(self, **params):
        if params.get('model') != 'gpt-5.6-luna' or params.get('previous_response_id'):
            raise RuntimeError('Live budget requires the configured model and self-contained input')
        if params.get('reasoning') != {'effort':'none'}:
            raise RuntimeError('Unexpected reasoning mode')
        if any(tool.get('type') != 'function' for tool in params.get('tools', [])):
            raise RuntimeError('Hosted billable tools are outside this budget')
        params['max_output_tokens'] = min(int(params.get('max_output_tokens', 1200)), 1200)
        params['service_tier'] = 'default'  # No project-level fast tier inheritance.
        params['store'] = False
        def serial(value):
            return value.model_dump(exclude_none=True) if hasattr(value,'model_dump') else str(value)
        payload = json.dumps(params, ensure_ascii=False, default=serial).encode('utf-8')
        if len(payload) > 48000 or b'input_image' in payload or b'input_audio' in payload:
            raise RuntimeError('Live request exceeds text-only bounded budget')
        # Standard short-context published maximum is $0.25/M input-cache-write
        # and $1.20/M output. Reserve $0.50/$3, input byte upper bound +8192
        # framing tokens, ignoring all cache discounts. Never refund reserves.
        reserve = ((len(payload)+8192)*0.50 + params['max_output_tokens']*3)/1_000_000
        if self.data['reserved_usd'] + reserve > self.LIMIT or len(self.data['calls']) >= 24:
            raise RuntimeError('Live credit reserve exhausted; no request sent')
        self.data['reserved_usd'] += reserve
        entry = {'case':self.case, 'phase':self.phase, 'source_commit':self.source_commit, 'request_bytes':len(payload),
                 'output_cap':params['max_output_tokens'], 'reserve_usd':reserve,
                 'status':'reserved_usage_unknown'}
        self.data['calls'].append(entry)
        self.save()  # Durable before network; a crash cannot forget a reservation.
        started = time.perf_counter()
        try:
            response = self.create_api(**params)
            from core.usage import extrair_metricas_uso
            metrics = extrair_metricas_uso(response)
            entry.update(status=getattr(response,'status','unknown'), usage=metrics)
            if metrics:
                estimate = (metrics['input_tokens']*0.25 + metrics['output_tokens']*1.20)/1_000_000
                entry['estimated_usd'] = estimate
                self.data['estimated_usd'] += estimate
                if metrics['input_tokens'] > len(payload)+8192:
                    raise RuntimeError('Budget input framing assumption invalid; stop')
            return response
        except Exception as exc:
            entry['error_type'] = type(exc).__name__
            entry['http_status'] = getattr(exc,'status_code',None)
            raise
        finally:
            entry['latency_ms'] = round((time.perf_counter()-started)*1000,3)
            self.save()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--case',choices=['greeting','maximize','youtube'],required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args()
    if not args.run:
        parser.error('Explicit --run is required for paid API and live effects')
    if os.getenv('OPENAI_BASE_URL'):
        raise RuntimeError('Custom endpoints are outside the verified pricing scope')
    from config import MODEL
    if MODEL!='gpt-5.6-luna':
        raise RuntimeError('Do not substitute the configured model')
    import openai
    from providers.openai_provider import OpenAIProvider
    from core.orchestrator import AurenOrchestrator
    from core.router import Router
    from core.harness import AurenHarness
    from core.task_manager import TaskManager
    from core.task_trace import TaskTraceStore
    from core.session import SessionContextManager
    from core.permission_manager import PermissionManager
    from tools import browser
    from tools.dispatcher import executar_ferramenta
    from core import harness_runtime as runtime

    args.evidence.mkdir(parents=True,exist_ok=True)
    folder=args.evidence/(args.case+'-'+uuid.uuid4().hex[:8]);folder.mkdir()
    runtime.LOG_DIR=folder/'logs';runtime.CHAT_LOGS_DIR=runtime.LOG_DIR/'chats'
    runtime.TASK_LOG_DIR=runtime.LOG_DIR/'tasks';runtime.LOG_FILE=runtime.LOG_DIR/'auren.log'
    provider=OpenAIProvider()
    real_client=provider.get_client()
    meter=LiveBudget(args.evidence/'budget.json',real_client.responses.create)
    meter.case=args.case
    meter.source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    provider._client=SimpleNamespace(responses=SimpleNamespace(create=meter.create))
    orchestrator=AurenOrchestrator(provider=provider,router=Router())
    title='AurenLiveFixture'+uuid.uuid4().hex[:10]
    root=None
    if args.case=='maximize':
        import tkinter as tk
        root=tk.Tk();root.title(title);root.geometry('500x250');root.update()
    if args.case=='youtube':
        browser.BROWSER_PROFILE_DIR=folder/'browser-profile'
    state={'first_id':None,'first_title':None,'confirmations':[],'executed':[]}

    def observe_first_video():
        if browser.pagina is None or '/results' not in browser.pagina.url:
            return
        cards=browser.pagina.locator('ytd-video-renderer a#video-title[href*="watch?v="]')
        if cards.count():
            state['first_title']=(cards.first.get_attribute('title') or cards.first.inner_text()).strip()
            state['first_id']=parse_qs(urlparse(cards.first.get_attribute('href')).query).get('v',[None])[0]

    def allowed(item):
        name=item.name
        try:
            data=json.loads(item.arguments)
        except (ValueError,TypeError):
            return False
        if args.case=='maximize':
            return name in {'maximizar_janela_windows','obter_geometria_janela_windows'} and data=={'alvo':title}
        if args.case!='youtube':
            return False
        if name=='navegar_navegador':
            parsed=urlparse(data.get('url',''))
            query=parse_qs(parsed.query)
            return (parsed.scheme=='https' and parsed.hostname in {'www.youtube.com','youtube.com'}
                and ((parsed.path in {'','/'} and not parsed.query)
                     or (parsed.path=='/results' and query.get('search_query')==['receitas de lasanha'])
                     or (parsed.path=='/watch' and state['first_id'] and query.get('v')==[state['first_id']])))
        if name in {'ler_pagina','obter_contexto_navegador','listar_abas'}:
            return True  # Dedicated public browser only, no personal profile.
        if name=='preencher_elemento':
            return data.get('texto')=='receitas de lasanha' and data.get('alvo','').casefold() in {'pesquisar','search','search_query'}
        if name=='pressionar_tecla':
            return data.get('tecla')=='Enter' and browser.pagina is not None and browser.pagina.evaluate(
                "() => document.activeElement?.getAttribute('name') === 'search_query'")
        if name=='clicar_elemento':
            observe_first_video()
            return data.get('indice',1)==1 and state['first_title'] is not None and data.get('alvo')==state['first_title']
        return False

    def confirm(request):
        # Explicit session authorization is restricted to opening the observed
        # first public recipe video. No generic positive confirmation channel.
        permitted=(args.case=='youtube' and request.tool_name=='clicar_elemento'
                   and state['first_id'] is not None and state['first_title'] is not None)
        state['confirmations'].append({'tool':request.tool_name,'allowed':permitted})
        return permitted

    pm=PermissionManager(confirmation_channel=SimpleNamespace(confirmar=confirm))
    def execute(item):
        result=executar_ferramenta(item,pm,None)
        state['executed'].append({'tool':item.name,'ok':result.ok,'error_code':result.error_code})
        if args.case=='youtube' and item.name in {'ler_pagina','obter_contexto_navegador'} and result.ok:
            observe_first_video()
        return result
    def model(entrada,response_id=None,reasoning_effort='none',tool_choice=None):
        meter.phase='principal'
        return orchestrator.create_response(entrada,response_id=response_id,
            reasoning_effort=reasoning_effort,tool_choice=tool_choice)
    def intent(*values):
        meter.phase='intent'
        return orchestrator.verify_intent(*values)
    def completion(*values):
        meter.phase='completion'
        return orchestrator.verify_completion(*values)
    h=AurenHarness(task_manager=TaskManager(db_path=folder/'tasks.sqlite3'),
        trace_store=TaskTraceStore(folder/'trace.sqlite3'),context=SessionContextManager(),
        permission_manager=pm,criar_resposta=model,verificar_intencao=intent,
        verificar_conclusao=completion,executar_ferramenta=execute,
        registrar_fonte_nao_confiavel=pm.registrar_fonte_nao_confiavel,
        obter_chamadas=lambda r:[i for i in r.output if getattr(i,'type','')=='function_call'],
        obter_metricas_roteamento=lambda:orchestrator.last_metrics,
        comando_rapido=lambda _:(False,''),mostrar_uso=lambda:None,iniciar_tarefa=pm.iniciar_tarefa,
        apos_tarefa=None,fechar=lambda:None,max_model_rounds=8)
    goal={'greeting':'ola auren','maximize':'maximize '+title,
          'youtube':'Abra o YouTube, pesquise receitas de lasanha e abra o primeiro video organico relevante da lista. Ignore anuncios e confirme a URL e o titulo do video aberto.'}[args.case]
    before=len(meter.data['calls']);started=time.perf_counter()
    try:
        _,answer=h.processar_mensagem(goal,execution_scope=allowed,model_budget=14)
        elapsed=(time.perf_counter()-started)*1000
        snapshot=h.current_task()
        independent={}
        if args.case=='maximize':
            import ctypes
            from ctypes import wintypes
            api=ctypes.windll.user32
            api.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];api.FindWindowW.restype=wintypes.HWND
            api.IsZoomed.argtypes=[wintypes.HWND]
            independent['maximized']=bool(api.IsZoomed(api.FindWindowW(None,title)))
        if args.case=='youtube' and browser.pagina is not None:
            parsed=urlparse(browser.pagina.url)
            independent={'watch_page':parsed.path=='/watch','video_matches_first':
                state['first_id'] is not None and parse_qs(parsed.query).get('v')==[state['first_id']],
                'title_matches_first':state['first_title'] is not None and state['first_title'] in browser.pagina.title()}
        observed=all(independent.values()) if independent else args.case=='greeting'
        result={'scenario':args.case,'source_commit':meter.source_commit,
            'model':MODEL,'sdk':openai.__version__,'duration_ms':round(elapsed,3),
            'task_state':snapshot.state.value,'task_error':snapshot.error.split(':')[0],
            'success':snapshot.state.value=='completed' and observed,
            'api_calls':len(meter.data['calls'])-before,'independent':independent,
            'executed':state['executed'],'confirmations':state['confirmations'],
            'reserved_total_usd':meter.data['reserved_usd'],
            'estimated_total_usd':meter.data['estimated_usd']}
        (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
        return 0 if result['success'] else 1
    finally:
        h.shutdown()
        if root is not None:root.destroy()
        if browser.browser_context is not None:browser.browser_context.close()
        if browser.playwright is not None:browser.playwright.stop()
        real_client.close()


if __name__=='__main__':
    raise SystemExit(main())
