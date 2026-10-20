"""Three actual checkouts, same synthetic world, intact Harness safety path.

No desktop/browser handlers survive initialization. --run is required for API;
--offline uses scripted model/review responses to validate fixtures and plumbing.
Parent runner rotates version order, serializes all calls through one ledger,
and never resets or reuses earlier authorizations.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS

SCRIPT=Path(__file__).resolve()
SPEC=importlib.util.spec_from_file_location('round2_budget',SCRIPT.with_name('discovery_round2_budget.py'))
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


def cases():
    return json.loads(SCRIPT.with_name('discovery_round2_cases.json').read_text(encoding='utf-8'))


def worker(args):
    sys.path.insert(0,str(Path.cwd()))
    from core.harness import AurenHarness
    from core.task_manager import TaskManager
    from core.permission_manager import PermissionManager
    from core.tool_result import ToolResult
    from core.session import SessionContextManager
    from core import harness_runtime as runtime
    from tools import dispatcher
    case=next(c for c in cases() if c['id']==args.case)
    name=f'{args.trial}-{args.case}-{args.variant}'
    folder=args.evidence/name;folder.mkdir()
    runtime.LOG_DIR=folder/'logs';runtime.CHAT_LOGS_DIR=runtime.LOG_DIR/'chats'
    runtime.TASK_LOG_DIR=runtime.LOG_DIR/'tasks';runtime.LOG_FILE=runtime.LOG_DIR/'auren.log'
    world={'active':1}
    def tabs():
        return ('Abas abertas: 2\nAba ativa: '+str(world['active'])+'\n'
            +'\n'.join(f'Aba {i}: Guia {title} | https://example.invalid/{slug}'+(' [ATIVA]' if i==world['active'] else '')
                         for i,title,slug in ((1,'Alfa','alfa'),(2,'Beta','beta'))))
    def page():
        return 'Titulo: Guia Beta\nCodigo: BETA-82' if world['active']==2 else 'Titulo: Guia Alfa\nCodigo: LIMA-27'
    def switch(parameters,*_):
        world['active']=parameters['indice']
        return ToolResult.success(f'Troquei para a aba {world["active"]}.',tool_name='trocar_aba')
    # Replace ALL terminal handlers. The actual catalog search remains metadata-only.
    for tool in list(dispatcher.TOOL_HANDLERS):
        if tool!='buscar_ferramentas':
            dispatcher.TOOL_HANDLERS[tool]=lambda *a:ToolResult.failure('Synthetic world refuses this tool',error_code='fixture_denied')
    handlers={
        'listar_janelas_windows':lambda *a:ToolResult.success('Janelas encontradas: 2\n1. Relatorio Sintetico\n2. Editor Sintetico'),
        'listar_abas':lambda *a:ToolResult.success(tabs()),
        'obter_audio_windows':lambda *a:ToolResult.success('Volume master: 42%\nMudo: desativado'),
        'ler_area_transferencia_windows':lambda *a:ToolResult.success('COPIA-53'),
        'buscar_arquivo':lambda *a:ToolResult.success('Arquivo encontrado: roteiro.txt | C:/SyntheticFixture/roteiro.txt'),
        'ler_pagina':lambda *a:ToolResult.success(page()),
        'obter_contexto_navegador':lambda *a:ToolResult.success(tabs()+'\n'+page(),data={'abas':tabs(),'pagina':page()}),
        'trocar_aba':switch,
    }
    dispatcher.TOOL_HANDLERS.update(handlers)
    selected_proposals=[];executed=[];rounds=[];turns=[];confirmations=[]
    def scope(item):
        if item.name=='buscar_ferramentas':return True
        if item.name not in case['scope']:return False
        try:data=json.loads(item.arguments)
        except (ValueError,TypeError):return False
        if item.name=='trocar_aba':return data=={'indice':2}
        if item.name=='buscar_arquivo':return 'roteiro' in str(data.get('consulta','')).lower()
        return True
    def confirm(request):
        item=current_item.get('value')
        allowed=item is not None and request.tool_name==item.name and scope(item)
        confirmations.append({'tool':request.tool_name,'allowed':allowed})
        return allowed
    pm=PermissionManager(confirmation_channel=NS(confirmar=confirm))
    current_item={}
    def execute(item):
        current_item['value']=item
        try:result=dispatcher.executar_ferramenta(item,pm,None)
        finally:current_item.clear()
        executed.append({'tool':item.name,'arguments':item.arguments,'ok':result.ok,'error':result.error_code})
        return result
    meter=None;client=None
    if not args.offline:
        if os.getenv('OPENAI_BASE_URL'):raise RuntimeError('Custom endpoint outside verified pricing')
        from providers.openai_provider import OpenAIProvider
        from core.orchestrator import AurenOrchestrator
        from core.router import Router
        import providers.openai_provider as provider_module
        provider_module.CACHE_KEY='pr173-round2-balanced'
        provider=OpenAIProvider();client=provider.get_client()
        meter=MODULE.RoundBudget(args.evidence/'budget.json',resume=True)
        meter.case=f'{args.case}-{args.trial}';meter.variant=args.variant
        provider._client=NS(responses=NS(create=lambda **kw:meter.create(client.responses.create,**kw)))
        orchestrator=AurenOrchestrator(provider=provider,router=Router())
        def model(entrada,response_id=None,reasoning_effort='none',tool_choice=None):
            meter.phase='principal'
            response=orchestrator.create_response(entrada,response_id=response_id,
                reasoning_effort=reasoning_effort,tool_choice=tool_choice)
            proposed=[{'tool':c.name,'arguments':c.arguments} for c in response.output if getattr(c,'type','')=='function_call']
            selected_proposals.extend(proposed)
            rounds.append(dict(orchestrator.last_metrics,schemas=list(orchestrator.router.last_tool_names),proposals=proposed))
            return response
        def intent(*v):meter.phase='intent';return orchestrator.verify_intent(*v)
        def completion(*v):meter.phase='completion';return orchestrator.verify_completion(*v)
    else:
        # Offline plumbing check; not a live success claim. Includes the actual
        # Router selection as well as real Dispatcher/contracts/permissions.
        from core.router import Router
        from core.tools_registry import tools
        from core.intent_verification import IntentDecision
        scripted=list(case['required'])
        n=[0]
        def model(entrada,**kw):
            names=Router().select_tool_names(entrada,tools)
            calls=[]
            if scripted:
                tool=scripted.pop(0);n[0]+=1
                parameters={'trocar_aba':{'indice':2},'ler_pagina':{'foco':'codigo'},
                    'buscar_arquivo':{'consulta':'roteiro.txt'}}.get(tool,{})
                c=NS(type='function_call',name=tool,arguments=json.dumps(parameters),call_id='f'+str(n[0]))
                calls=[c];selected_proposals.append({'tool':tool,'arguments':c.arguments})
            return NS(output=calls,output_text=' '.join(case['facts']) if not calls else '',usage=None)
        intent=lambda *a:IntentDecision('aprovar','Synthetic coherent step')
        completion=None  # offline checks safety plumbing, not semantic-review quality
    h=AurenHarness(criar_resposta=model,executar_ferramenta=execute,verificar_intencao=intent,
        verificar_conclusao=completion,permission_manager=pm,task_manager=TaskManager(),context=SessionContextManager(),
        mostrar_uso=lambda:None,obter_chamadas=lambda r:[c for c in r.output if getattr(c,'type','')=='function_call'],
        comando_rapido=lambda m:(False,''),iniciar_tarefa=pm.iniciar_tarefa,apos_tarefa=None,fechar=lambda:None,
        registrar_fonte_nao_confiavel=pm.registrar_fonte_nao_confiavel,
        obter_metricas_roteamento=(lambda:orchestrator.last_metrics) if meter else None,max_model_rounds=6)
    first_call=len(meter.data['calls']) if meter else 0
    start=time.perf_counter()
    try:
        final_text=''
        for prompt in case['turns']:
            _,answer=h.processar_mensagem(prompt,execution_scope=scope,model_budget=8)
            final_text=str(getattr(answer,'output_text',answer));task=h.current_task()
            turns.append({'state':task.state.value,'error':task.error,'answer_chars':len(final_text)})
            if task.state.value!='completed':break
        observed={e['tool'] for e in executed if e['ok']}
        required=set(case['required'])
        facts_ok=all(f.casefold() in final_text.casefold() for f in case['facts'])
        action_ok=required<=observed and (not case.get('active_tab') or world['active']==case['active_tab'])
        refusal_ok=(not case.get('refusal') or (not (observed-{'buscar_ferramentas'})
            and any(w in final_text.casefold() for w in ('nao','não','imposs','indispon','consigo','posso','capacidade'))))
        operational=[p['tool'] for p in selected_proposals if p['tool']!='buscar_ferramentas']
        correct_selection=all(p['tool'] in case['scope'] for p in selected_proposals if p['tool']!='buscar_ferramentas')
        usage=meter.data['calls'][first_call:] if meter else []
        result={'case':args.case,'split':case['split'],'trial':args.trial,'variant':args.variant,
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'paid':not args.offline,'real_terminal_effects':0,'turns':turns,'executed':executed,'rounds':rounds,
            'first_operational_tool':operational[0] if operational else None,'correct_selection':correct_selection,
            'required_observed':action_ok,'facts_ok':facts_ok,'refusal_ok':refusal_ok,
            'success':len(turns)==len(case['turns']) and all(t['state']=='completed' for t in turns)
                      and action_ok and facts_ok and refusal_ok and correct_selection,
            'duration_ms':round((time.perf_counter()-start)*1000,3),'api_calls':len(usage),
            'confirmations':confirmations,'usage_numbers':[u['number'] for u in usage],
            'estimated_usd':sum(u.get('estimated_usd',0) for u in usage),
            'cache_neutral_usd':sum(u.get('cache_neutral_usd',0) for u in usage),
            **{k:sum(u.get(k,0) for u in usage) for k in ('input_tokens','output_tokens','cached_tokens','cache_write_tokens','reasoning_tokens')}}
        (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in {'executed','rounds','confirmations'}},ensure_ascii=True),flush=True)
    finally:
        h.shutdown()
        if client:client.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--offline',action='store_true')
    p.add_argument('--worker',action='store_true');p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--base',type=Path);p.add_argument('--current',type=Path);p.add_argument('--case')
    p.add_argument('--variant',default='candidate');p.add_argument('--trial',type=int,default=0)
    p.add_argument('--repeats',type=int,default=1);p.add_argument('--split',choices=['development','heldout','all'],default='all')
    args=p.parse_args();args.evidence=args.evidence.resolve()
    if not(args.run or args.offline):p.error('--run for paid API or --offline required')
    if args.worker:return worker(args)
    selected=[c for c in cases() if args.split=='all' or c['split']==args.split]
    variants=[('base',args.base),('current',args.current),('candidate',SCRIPT.parents[2])]
    if args.offline:variants=[variants[-1]]
    if any(root is None for _,root in variants):p.error('--base and --current required')
    args.evidence.mkdir(parents=True,exist_ok=True)
    manifest={'cases_sha256':hashlib.sha256(SCRIPT.with_name('discovery_round2_cases.json').read_bytes()).hexdigest(),
        'order':'cyclic Latin order by case+trial; serial calls; identical synthetic world',
        'variants':{v:str(root) for v,root in variants},'split':args.split,'repeats':args.repeats}
    manifest_path=args.evidence/('manifest-'+args.split+('-offline' if args.offline else '')+'.json')
    with manifest_path.open('x',encoding='utf-8') as stream:json.dump(manifest,stream,indent=2)
    for trial in range(args.repeats):
        for i,case in enumerate(selected):
            rotation=(i+trial)%len(variants)
            for variant,root in variants[rotation:]+variants[:rotation]:
                env=dict(os.environ,AUREN_TEST_MODE='1')
                if variant!='base':env['AUREN_DYNAMIC_TOOL_DISCOVERY']='1'
                else:env.pop('AUREN_DYNAMIC_TOOL_DISCOVERY',None)
                if variant=='candidate':env['AUREN_DISCOVERY_POLICY']='bootstrap'
                else:env.pop('AUREN_DISCOVERY_POLICY',None)
                cmd=[sys.executable,str(SCRIPT),'--worker','--evidence',str(args.evidence),
                     '--case',case['id'],'--variant',variant,'--trial',str(trial),
                     '--offline' if args.offline else '--run']
                done=subprocess.run(cmd,cwd=root,env=env,timeout=240)
                if done.returncode:raise RuntimeError('Worker failed; stop batch, retain shared ledger')
                if not args.offline:MODULE.RoundBudget(args.evidence/'budget.json',resume=True)


if __name__=='__main__':main()
