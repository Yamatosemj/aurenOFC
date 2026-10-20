"""Aggregate offline context evidence and reject unequal comparison traces."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


def summarize(folder):
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*-base.json'))]
    result={'token_method':'tiktoken 0.12.0 o200k_base component proxy; not provider usage',
            'actual_api_calls':0,'paid_usd':0,'actual_cache_tokens':None,
            'actual_cache_writes':None,'actual_api_latency_ms':None,
            'reference_rates_per_million':{'input':.20,'cached':.02,'cache_write':.25,'output':1.20},
            'variants':{},'pairs':[]}
    for variant in ('base','reviews','plan','combined'):
        group=[]
        for baseline in rows:
            item=json.loads((folder/f'{baseline["case"]}-{variant}.json').read_text(encoding='utf-8'))
            assert item['scripted_success'] and baseline['scripted_success']
            assert item['turns']==baseline['turns'], (item['case'],variant,'effects/facts/state changed')
            assert item['context_builds']==baseline['context_builds']
            assert item['phases']==baseline['phases']
            for a,b in zip(item['requests'],baseline['requests']):
                for key in ('phase','instructions_sha256','schemas_sha256','previous_response_id','cache_options'):
                    assert a[key]==b[key],(item['case'],variant,key)
            result['pairs'].append({'case':item['case'],'variant':variant,
                'input_tokens_proxy':item['input_tokens_proxy'],
                'saved_input_proxy':baseline['input_tokens_proxy']-item['input_tokens_proxy'],
                'output_tokens_proxy':item['output_tokens_proxy'],
                'fake_calls':item['calls_to_fake_transport'],
                'offline_duration_ms':item['offline_duration_ms'],'scripted_success':True})
            group.append(item)
        total_in=sum(i['input_tokens_proxy'] for i in group)
        total_out=sum(i['output_tokens_proxy'] for i in group)
        components=Counter()
        phases=Counter()
        for item in group:
            for req in item['requests']:
                phases[req['phase']]+=1
                for name,size in req['components'].items():
                    components[name]+=size['tokens_proxy']
        result['variants'][variant]={'trials':len(group),'tasks':sum(len(i['turns']) for i in group),
            'scripted_success':len(group),'fake_calls':sum(i['calls_to_fake_transport'] for i in group),
            'input_tokens_proxy':total_in,'output_tokens_proxy':total_out,
            'total_tokens_proxy':total_in+total_out,'phases':dict(phases),
            'components_input_proxy':dict(components),
            'offline_median_ms':median(i['offline_duration_ms'] for i in group),
            'hypothetical_usd_all_input_uncached':(total_in*.20+total_out*1.20)/1e6,
            'hypothetical_usd_all_input_cache_write':(total_in*.25+total_out*1.20)/1e6,
            'hypothetical_usd_all_input_cached':(total_in*.02+total_out*1.20)/1e6}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    args=p.parse_args();result=summarize(args.folder)
    (args.folder/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['variants'],indent=2))
