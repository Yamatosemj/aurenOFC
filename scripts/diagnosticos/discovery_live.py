"""API-real A/B, ONLY in-memory terminal fixtures. No browser/Windows effects.

All model/review calls use the same durable PR173 ledger. Run once with --run
--baseline <isolated baseline checkout> --evidence <new directory>.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS

SCRIPT=Path(__file__).resolve()
spec=importlib.util.spec_from_file_location('pr173_budget',SCRIPT.with_name('discovery_live_budget.py'))
budget_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget_module)
DiscoveryBudget=budget_module.DiscoveryBudget


def worker(args):
    sys.path.insert(0,str(Path.cwd()))
    if os.getenv('OPENAI_BASE_URL'):raise RuntimeError('Custom endpoint outside pricing scope')
    from providers.openai_provider import OpenAIProvider
    from core.orchestrator import AurenOrchestrator
    from core.router import Router
    from core.harness import AurenHarness
    from core.permission_manager import PermissionManager
    from core.task_manager import TaskManager
    from core.tool_result import ToolResult
    from core import harness_runtime as runtime
    from tools import dispatcher
    folder=args.evidence/(args.mode+'-'+args.case);folder.mkdir()
    runtime.LOG_DIR=folder/'logs';runtime.CHAT_LOGS_DIR=runtime.LOG_DIR/'chats'
    runtime.TASK_LOG_DIR=runtime.LOG_DIR/'tasks';runtime.LOG_FILE=runtime.LOG_DIR/'auren.log'
    # Replace EVERY terminal handler before creating a model. Only catalog
    # search remains real. Even a scope or test bug cannot touch the desktop.
    for name in list(dispatcher.TOOL_HANDLERS):
        if name!='buscar_ferramentas':
            dispatcher.TOOL_HANDLERS[name]=lambda *a:ToolResult.failure('Fixture refuses this tool',error_code='fixture_denied')
    dispatcher.TOOL_HANDLERS['listar_janelas_windows']=lambda *a:ToolResult.success(
        'Janelas encontradas: 2\n1. Relatorio Sintetico\n2. Editor Sintetico',tool_name='listar_janelas_windows')
    pm=PermissionManager(confirmation_channel=NS(confirmar=lambda _:False))
    provider=OpenAIProvider();client=provider.get_client()
    meter=DiscoveryBudget(args.evidence/'budget.json',resume=True)
    meter.mode=args.mode;meter.case=args.case
    provider._client=NS(responses=NS(create=lambda **kw:meter.create(client.responses.create,**kw)))
    orchestrator=AurenOrchestrator(provider=provider,router=Router())
    rounds=[];executed=[]
    def model(entrada,response_id=None,reasoning_effort='none',tool_choice=None):
        meter.phase='principal'
        result=orchestrator.create_response(entrada,response_id=response_id,reasoning_effort=reasoning_effort,tool_choice=tool_choice)
        rounds.append(dict(orchestrator.last_metrics,schemas=list(orchestrator.router.last_tool_names)))
        return result
    def intent(*v):meter.phase='intent';return orchestrator.verify_intent(*v)
    def completion(*v):meter.phase='completion';return orchestrator.verify_completion(*v)
    def execute(item):
        result=dispatcher.executar_ferramenta(item,pm,None)
        executed.append({'tool':item.name,'ok':result.ok,'error':result.error_code})
        return result
    h=AurenHarness(criar_resposta=model,executar_ferramenta=execute,verificar_intencao=intent,
        verificar_conclusao=completion,permission_manager=pm,task_manager=TaskManager(),
        mostrar_uso=lambda:None,obter_chamadas=lambda r:[c for c in r.output if getattr(c,'type','')=='function_call'],
        comando_rapido=lambda m:(False,''),iniciar_tarefa=pm.iniciar_tarefa,apos_tarefa=None,fechar=lambda:None,
        obter_metricas_roteamento=lambda:orchestrator.last_metrics,max_model_rounds=5)
    prompts={'greeting':'ola auren','discovery':'Mostre os titulos abertos.',
             'unsupported':'Acione o teletransporte quantico para Marte.'}
    before=len(meter.data['calls']);start=time.perf_counter()
    try:
        _,answer=h.processar_mensagem(prompts[args.case],
            execution_scope=lambda c:c.name in {'buscar_ferramentas','listar_janelas_windows'},model_budget=5)
        task=h.current_task();text=str(getattr(answer,'output_text',answer))
        fixture_observed=(any(e['tool']=='listar_janelas_windows' and e['ok'] for e in executed)
                          and 'Relatorio Sintetico' in text and 'Editor Sintetico' in text)
        result={'mode':args.mode,'case':args.case,'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'task_state':task.state.value,'error':task.error,'calls':len(meter.data['calls'])-before,
            'duration_ms':round((time.perf_counter()-start)*1000,3),'rounds':rounds,'executed':executed,
            'fixture_observed':fixture_observed,'answer':text,'real_terminal_effects':0,
            'limitation':'Real API; synthetic handlers, no real UI/Windows success claim'}
        (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True),flush=True)
    finally:h.shutdown();client.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--worker',action='store_true')
    p.add_argument('--baseline',type=Path);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--mode',choices=['baseline','proposed']);p.add_argument('--case',choices=['greeting','discovery','unsupported'])
    args=p.parse_args()
    if not args.run:p.error('--run required for paid calls')
    args.evidence=args.evidence.resolve()
    if args.worker:return worker(args)
    if not args.baseline:p.error('--baseline required')
    DiscoveryBudget(args.evidence/'budget.json')
    for case in ('greeting','discovery','unsupported'):
        for mode,root in [('baseline',args.baseline.resolve()),('proposed',SCRIPT.parents[2])]:
            env=dict(os.environ,AUREN_TEST_MODE='1')
            if mode=='proposed':env['AUREN_DYNAMIC_TOOL_DISCOVERY']='1'
            else:env.pop('AUREN_DYNAMIC_TOOL_DISCOVERY',None)
            result=subprocess.run([sys.executable,str(SCRIPT),'--run','--worker','--mode',mode,'--case',case,
                '--evidence',str(args.evidence)],cwd=root,env=env,timeout=180)
            if result.returncode:raise RuntimeError('Worker failed; stop all further spending')
            ledger=json.loads((args.evidence/'budget.json').read_text(encoding='utf-8'))
            if any(c['status']!='received' for c in ledger['calls']):raise RuntimeError('Unknown usage; stop')


if __name__=='__main__':main()
