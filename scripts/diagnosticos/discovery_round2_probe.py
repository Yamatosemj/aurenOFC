"""Selection-only ablations before runtime changes. NEVER executes a tool.

Run offline without --run. Paid mode uses the independent shared round-2 ledger.
goal_only is a diagnostic input ablation, never a production security change.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent


def state_for(prompt):
    from core.harness_state import _montar_estado
    return _montar_estado(prompt, [], incluir_contexto=True, contexto_tarefa='',
        vision_reobserve_pending=False, max_history_items=2, max_state_chars=4500,
        texto_seguro=lambda text,limit:text[:limit])


def select(strategy, prompt, registered):
    from core.router import Router, COMMON_TOOLS
    from core.tool_discovery import SEARCH_NAME, search_catalog
    router=Router()
    selected=router.select_tools(state_for(prompt),registered)
    if strategy=='dense':return [t for t in registered if t['name']!=SEARCH_NAME]
    if strategy in {'current','goal_only'}:return selected
    if not selected:return selected
    names={t['name'] for t in selected}
    # Existing broad domain routes are retained in these shadow candidates.
    if names=={SEARCH_NAME}:
        names |= COMMON_TOOLS | {'listar_abas','obter_audio_windows'}
        if strategy=='prefetch':
            result=search_catalog(prompt[:180],3,registered)
            names.update(t['nome'] for t in result.data['ferramentas'])
    result=[deepcopy(t) for t in registered if t['name'] in names]
    if strategy=='catalog':
        catalog='\nCATALOGO LOCAL (nomes, nao permissoes):\n'+'\n'.join(
            t['name']+': '+t.get('description','').split('. ')[0][:100]
            for t in registered if t['name'] not in names)
        for tool in result:
            if tool['name']==SEARCH_NAME:tool['description']+=catalog
    return result


PROMPTS={'ambiguous':'Mostre os titulos abertos.',
    'titles':'Mostre os titulos dos aplicativos visiveis no computador.',
    'unsupported':'Acione o teletransporte quantico para Marte.',
    'audio':'Qual o volume e o estado de mudo atuais?',
    'compound':'Liste as abas do navegador e consulte o arquivo relatorio.txt.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true')
    p.add_argument('--strategy',choices=['current','goal_only','anchors','catalog','prefetch','dense'],default='current')
    p.add_argument('--prompt-id',choices=PROMPTS,default='titles');p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--trial',default='0');args=p.parse_args()
    sys.path.insert(0,str(Path.cwd()))
    from core.tools_registry import tools
    from core.prompt import instrucoes
    prompt=PROMPTS[args.prompt_id]
    if not args.run:
        result={'instructions_chars':len(instrucoes),'state_chars':len(state_for(prompt)),
            'cases':{key:{strategy:{'names':[t['name'] for t in select(strategy,goal,tools)],
                'schema_chars':len(json.dumps(select(strategy,goal,tools),ensure_ascii=False))}
                for strategy in ('current','anchors','catalog','prefetch','dense')} for key,goal in PROMPTS.items()}}
        from core.tool_discovery import search_catalog
        result['previous_model_queries']=[{'query':q,'result':dict(search_catalog(q,5,tools).data)} for q in (
            'listar títulos das abas abertas no navegador',
            'capturar a tela atual e identificar os títulos dos aplicativos/janelas visíveis no computador',
            'encontrar e acionar o controle de teletransporte quântico para Marte na interface visível')]
        args.evidence.mkdir(parents=True,exist_ok=True)
        (args.evidence/'offline-diagnosis.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in {'cases','previous_model_queries'}}))
        return
    import os
    if os.getenv('OPENAI_BASE_URL'):raise RuntimeError('Custom endpoint not authorized')
    spec=importlib.util.spec_from_file_location('budget2',HERE/'discovery_round2_budget.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    meter=mod.RoundBudget(args.evidence/'budget.json',resume=True)
    meter.case='probe-'+args.prompt_id+'-'+args.trial;meter.variant=args.strategy;meter.phase='selection-only'
    from openai import OpenAI
    selected=select(args.strategy,prompt,tools)
    start=time.perf_counter()
    with OpenAI(max_retries=0,timeout=45.) as client:
        response=meter.create(client.responses.create,model=meter.MODEL,instructions=instrucoes,
            input=prompt if args.strategy=='goal_only' else state_for(prompt),tools=selected,
            reasoning={'effort':'none'},prompt_cache_key='pr173-round2-balanced',parallel_tool_calls=True)
    result={'case':meter.case,'variant':args.strategy,'selection_only':True,'real_effects':0,
        'elapsed_ms':round((time.perf_counter()-start)*1000,3),'schemas':[t['name'] for t in selected],
        'calls':[{'name':c.name,'arguments':c.arguments} for c in response.output if getattr(c,'type','')=='function_call'],
        'answer_chars':len(response.output_text),'usage':meter.data['calls'][-1]}
    path=args.evidence/(meter.case+'-'+args.strategy+'.json')
    with path.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,ensure_ascii=False)
    print(json.dumps({k:v for k,v in result.items() if k not in {'schemas','usage'}},ensure_ascii=True))


if __name__=='__main__':main()
