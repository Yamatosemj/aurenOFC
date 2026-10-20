"""Execute production UI functions with a tiny DOM and controlled HTTP ordering."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('initial', ['off', 'standby'])
@pytest.mark.parametrize('poll_first', [False, True])
def test_message_and_poll_keep_header_in_sync(initial, poll_first):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node unavailable; no downloads allowed')
    html = (Path(__file__).resolve().parents[1] / 'ui/chrome.html').read_text(encoding='utf-8')
    conversation = html[html.index('async function conversar('):html.index('\n/* barra de busca:')]
    event_functions = html[html.index('function pintaModo('):html.index('\nconst connection=')]
    program = r'''
const vm=require('vm'),assert=require('assert/strict');
const elements={};
const $=id=>elements[id]||(elements[id]={textContent:'',hidden:true});
let resolvePost;
const ctx={$,cap:$('legenda'),eco:$('eco'),seq:0,idle:0,clearTimeout(){},
  define(){},agir(_m,text){ctx.cap.textContent=text},modoAtual:INITIAL,
  ocupado:false,ultimoEvento:0,consultando:false,pedidoPendente:null,
  taskGeneration:0,AUREN_TOKEN:'discardable',renderTasks(){},renderNotifications(){},
  postApi:()=>new Promise(resolve=>{resolvePost=resolve}),
  fetch:async()=>({ok:true,json:async()=>({mode:'active',busy:false,events:[
    {seq:1,kind:'reply',text:'Resposta preservada'}],generation:1,tasks:{}})})};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
(async()=>{
  ctx.pintaModo();
  const sending=ctx.conversar('ola');
  if(POLL_FIRST)await ctx.eventos();
  resolvePost({accepted:true,mode:'active'});await sending;
  await ctx.eventos();
  assert.equal($('bEstados').textContent,'Ativo');
  assert.equal(ctx.cap.textContent,'Resposta preservada');
  // Immediate off feedback must still work without waiting for the next poll.
  ctx.postApi=async()=>({accepted:true,mode:'off'});
  await ctx.conversar('sair');
  assert.equal($('bEstados').textContent,'Desligado');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('INITIAL', json.dumps(initial)).replace('POLL_FIRST', json.dumps(poll_first)).replace('SOURCE', json.dumps(conversation + '\n' + event_functions))
    result = subprocess.run([node, '-e', program], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
