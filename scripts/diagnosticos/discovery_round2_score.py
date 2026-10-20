"""Offline audit of immutable raw trials; no model calls or runtime changes.

Report both initial strict-name scoring and capability-equivalent scoring.
Accent normalization follows Auren's existing name matching. A browser context
read includes the same synthetic page as ler_pagina. Source logs stay local.
"""
import argparse
import json
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from core.utils import normalizar_nome


def final_text(folder, result):
    if result['turns'][-1]['state']!='completed':return '', 'not_completed'
    length=result['turns'][-1]['answer_chars']
    text=(folder/'logs'/'auren.log').read_text(encoding='utf-8')
    for field in ('output_text','resultado'):
        lines=re.findall(r'^  '+field+r': (.+)$',text,re.M)
        for line in reversed(lines):
            try:value=json.loads(line)
            except ValueError:continue
            if isinstance(value,str) and len(value)==length:
                return value,field
    return '', 'not_reconstructed'


def audit(folder,result,case):
    text,source=final_text(folder,result)
    norm=normalizar_nome(text)
    facts=all(normalizar_nome(f) in norm for f in case['facts'])
    # Requirements are about observations/effects, not a preferred tool name.
    observed={e['tool'] for e in result['executed'] if e['ok']}
    equivalent=set(observed)
    if 'obter_contexto_navegador' in equivalent:
        equivalent.update({'ler_pagina','listar_abas'})
    effects=[json.loads(e['arguments'])['indice'] for e in result['executed'] if e['tool']=='trocar_aba' and e['ok']]
    active_ok=not case.get('active_tab') or bool(effects and effects[-1]==case['active_tab'])
    observations=set(case['required'])<=equivalent and active_ok
    if 'audio' in case['id']:
        facts=facts and bool(re.search(r'nao.{0,30}silenciad|mudo.{0,20}desativad|mudo.{0,10}nao',norm))
    if case['id']=='heldout_tabs':
        facts=facts and all(url in text for url in ('https://example.invalid/alfa','https://example.invalid/beta'))
    success=(len(result['turns'])==len(case['turns']) and all(t['state']=='completed' for t in result['turns'])
        and facts and observations and result['refusal_ok'] and result['correct_selection'])
    return dict(result,raw_success=result['success'],audited_success=success,
        audited_facts_ok=facts,capability_observed=observations,answer_source=source)


def summarize(rows):
    output={}
    for variant in sorted({r['variant'] for r in rows}):
        group=[r for r in rows if r['variant']==variant]
        output[variant]={'tasks':len(group),'successes':sum(r['audited_success'] for r in group),
            'strict_raw_successes':sum(r['raw_success'] for r in group),
            'correct_selection':sum(r['correct_selection'] for r in group),
            'median_ms':statistics.median(r['duration_ms'] for r in group),
            **{k:sum(r[k] for r in group) for k in ('input_tokens','output_tokens','api_calls',
                'estimated_usd','cache_neutral_usd','cached_tokens','cache_write_tokens')}}
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--cases',type=Path,default=Path(__file__).with_name('discovery_round2_cases.json'))
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    lookup={c['id']:c for c in json.loads(args.cases.read_text(encoding='utf-8'))}
    rows=[]
    for path in sorted(args.evidence.glob('*/result.json')):
        d=json.loads(path.read_text(encoding='utf-8'))
        if d['paid']:rows.append(audit(path.parent,d,lookup[d['case']]))
    result={'method':'raw results retained; Unicode name normalization; page/context equivalence; full task state and independent fixture facts required',
        'summary':summarize(rows),'heldout_summary':summarize([r for r in rows if r['split']=='heldout']),
        'rows':rows}
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
