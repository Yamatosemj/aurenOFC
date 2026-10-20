"""Policy changes visibility only; old default and flag-off remain unchanged."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]


def isolated(code, *, enabled=True):
    env=dict(os.environ,AUREN_DISCOVERY_POLICY='bootstrap',AUREN_TEST_MODE='1')
    if enabled:env['AUREN_DYNAMIC_TOOL_DISCOVERY']='1'
    else:env.pop('AUREN_DYNAMIC_TOOL_DISCOVERY',None)
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,
        capture_output=True,text=True,timeout=35)
    assert result.returncode==0,result.stdout+result.stderr


def test_bootstrap_contains_cheap_reads_and_registered_search_only():
    isolated('''
from core.router import Router, DISCOVERY_BOOTSTRAP_TOOLS
from core.tools_registry import tools
from core.tool_discovery import SEARCH_NAME
router=Router()
for prompt in ('Mostre os titulos dos aplicativos visiveis no computador.', 'quais guias estao abertas?', 'faca isso', 'zzzzqqqq'):
    names=set(router.select_tool_names(prompt,tools))
    assert names==DISCOVERY_BOOTSTRAP_TOOLS|{SEARCH_NAME}, names
    assert len(names)==6
    assert names<={t['name'] for t in tools}
assert router.select_tools('oi',tools)==[]
assert router.select_tool_names('faca isso',[])==[]
''')


def test_policy_cannot_enable_discovery_without_main_flag():
    isolated('''
from core.router import Router
from core.tools_registry import tools
assert 'buscar_ferramentas' not in {t['name'] for t in tools}
assert Router().select_tool_names('faca isso',tools)==[t['name'] for t in tools]
''',enabled=False)


def test_registered_tool_is_dynamically_loaded_without_replacing_compound_domains():
    isolated('''
import json
from types import SimpleNamespace as NS
from core.router import Router
from core.tools_registry import tools
from core.tool_discovery import SEARCH_NAME, search_catalog
r=Router()
extra={'name':'consultar_observatorio','type':'function','description':'Consulta astronomia de observatorio remoto.',
       'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False},'strict':True}
registered=tools+[extra]
assert extra['name'] not in r.select_tool_names('faca isso',registered)
args={'consulta':'consultar_observatorio','limite':1}
call=NS(type='function_call',name=SEARCH_NAME,call_id='search',arguments=json.dumps(args))
result=search_catalog(**args,registered=registered)
state={'role':'user','content':[{'type':'input_text','text':'CONTEXTO CONTROLADO DA TAREFA\\nObjetivo original: leia a pagina e o arquivo relatorio.txt\\n'}]}
inp=[state,call,{'type':'function_call_output','call_id':'search','output':result.for_model()}]
names=r.select_tool_names(inp,registered)
assert {extra['name'],'ler_pagina','ler_arquivo',SEARCH_NAME}<=set(names)
assert extra['name'] not in r.select_tool_names('faca isso',registered) # same Router, new task
''')


def test_bootstrap_visibility_never_overrides_dispatcher_permission_or_scope():
    isolated('''
from types import SimpleNamespace as NS
from core.router import Router
from core.tools_registry import tools
from core.permission_manager import PermissionManager
from core.execution_scope import current_scope
from tools import dispatcher
assert 'listar_abas' in Router().select_tool_names('faca isso',tools)
seen=[]
dispatcher.TOOL_HANDLERS['listar_abas']=lambda *a:seen.append(1)
token=current_scope.set(lambda c:False)
try:
    result=dispatcher.executar_ferramenta(NS(name='listar_abas',arguments='{}'),PermissionManager(),None)
    assert not result.ok and result.error_code=='execution_scope_denied' and not seen
finally:current_scope.reset(token)
pm=PermissionManager();pm.autorizar=lambda *a:(False,'synthetic denial')
result=dispatcher.executar_ferramenta(NS(name='listar_abas',arguments='{}'),pm,None)
assert not result.ok and result.error_code=='permission_denied' and not seen
''')
