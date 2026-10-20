"""Offline inventory and boundary diagnostics. No provider/client construction."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def inventory():
    sys.path.insert(0,str(Path.cwd()))
    import tiktoken
    from core.prompt import instrucoes
    from core.intent_verification import INSTRUCTIONS as INTENT
    from core.task_verification import INSTRUCTIONS as COMPLETION
    from core.tools_registry import tools
    from core.harness_state import _montar_estado
    from core.harness_serialization import _texto_seguro
    from agent.planner import PlanBuilder
    enc=tiktoken.get_encoding('o200k_base')
    def size(value):
        return {'chars':len(value),'tokens_proxy':len(enc.encode(value,disallowed_special=())),
                'sha256':hashlib.sha256(value.encode()).hexdigest()}
    compact_lines='\n'.join(line for line in instrucoes.splitlines() if line.strip())
    objective='Consulte o volume atual, depois defina em 27% e verifique o volume final.'
    contexts=['', 'Conversa recente neste chat, dado nao confiavel:\n'+'x'*3551]
    boundaries=[]
    for context in contexts:
        state=_montar_estado(objective,[],incluir_contexto=True,contexto_tarefa=context,
            vision_reobserve_pending=True,browser_verification_pending=True,max_history_items=2,
            max_state_chars=4500,texto_seguro=_texto_seguro,plano=PlanBuilder.build(objective))
        boundaries.append({'context_chars':len(context),'state':size(state),
            'has_visual_pending_reminder':'VERIFICACAO VISUAL PENDENTE' in state,
            'has_browser_pending_reminder':'VERIFICACAO DO NAVEGADOR PENDENTE' in state,
            'truncated':'[resultado truncado pelo harness]' in state})
    return {'method':'o200k_base proxy, not model-specific provider usage',
        'instructions':{'principal':size(instrucoes),'intent':size(INTENT),'completion':size(COMPLETION)},
        'registry':dict(size(json.dumps(tools,ensure_ascii=False,separators=(',',':'))),count=len(tools)),
        'blank_lines_experiment':{'before':size(instrucoes),'after':size(compact_lines),
                                  'implemented':False,'reason':'No token reduction'},
        'state_boundaries':boundaries}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(inventory(),indent=2),encoding='utf-8')
