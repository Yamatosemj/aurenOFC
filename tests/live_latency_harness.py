"""Full Harness with real isolated Win32 window, scripted model/review, no API.

One run per revision; not a measurement of network/model generation latency.
"""
import argparse
import gc
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
import uuid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not args.run:
        parser.error('Explicit --run required: creates/destroys its own window.')
    sys.path.insert(0,str(args.repo.resolve()))
    from core.harness import AurenHarness
    from core.task_manager import TaskManager
    from core.task_trace import TaskTraceStore
    from core.permission_manager import PermissionManager
    from core.session import SessionContextManager
    from core.intent_verification import IntentDecision
    from tools.dispatcher import executar_ferramenta
    title='Auren latency Fixture '+uuid.uuid4().hex[:10]
    root=tk.Tk();root.title(title);root.geometry('500x250');root.update()
    counts={'principal_calls':0,'intent_reviews':0,'completion_reviews':0}
    def model(*_):
        counts['principal_calls']+=1
        if counts['principal_calls']<=2:
            name='maximizar_janela_windows' if counts['principal_calls']==1 else 'obter_geometria_janela_windows'
            return SimpleNamespace(output=[SimpleNamespace(type='function_call',name=name,
                arguments=json.dumps({'alvo':title}),call_id=str(counts['principal_calls']))],output_text='',usage=None)
        return SimpleNamespace(output=[],output_text='Janela maximizada: '+title,usage=None)
    def intent(*_):
        counts['intent_reviews']+=1
        return IntentDecision('aprovar','scripted exact target')
    def completion(snapshot):
        counts['completion_reviews']+=1
        return {'summary':'scripted evidence check','answer_status':'verified',
            'steps':[{'index':s.index,'status':'verified',
                'evidence':list(range(1,len(snapshot.steps)+1))} for s in snapshot.plan.steps]}
    try:
        with tempfile.TemporaryDirectory(prefix='auren-latency-harness-') as folder:
            pm=PermissionManager()
            h=AurenHarness(task_manager=TaskManager(db_path=Path(folder)/'tasks.sqlite3'),
                trace_store=TaskTraceStore(Path(folder)/'trace.sqlite3'),permission_manager=pm,
                context=SessionContextManager(),criar_resposta=model,verificar_intencao=intent,
                verificar_conclusao=completion,
                executar_ferramenta=lambda item:executar_ferramenta(item,pm,None),
                obter_chamadas=lambda r:r.output,comando_rapido=lambda _:(False,''),
                mostrar_uso=lambda:None,iniciar_tarefa=pm.iniciar_tarefa,
                apos_tarefa=None,fechar=lambda:None,max_model_rounds=5)
            started=time.perf_counter()
            try:
                _,answer=h.processar_mensagem('maximize '+title)
                duration=(time.perf_counter()-started)*1000
                snapshot=h.current_task()
                user32=ctypes.windll.user32
                user32.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR]
                user32.FindWindowW.restype=wintypes.HWND
                user32.IsZoomed.argtypes=[wintypes.HWND]
                observed=bool(user32.IsZoomed(user32.FindWindowW(None,title)))
                result={'mode':'real_win32_scripted_model_harness','duration_ms':round(duration,3),
                    'status':snapshot.state.value,'window_maximized':observed,
                    'executed_steps':len(snapshot.steps),'reserved_calls':snapshot.model_calls,
                    'api_cost_usd':0,**counts}
                print(json.dumps(result))
                return 0 if snapshot.state.value=='completed' and observed else 1
            finally:
                h.shutdown()
                # Historical trace code held SQLite connections in cycles.
                # Release this probe's handles before TemporaryDirectory cleanup.
                gc.collect()
    finally:
        root.destroy()


if __name__=='__main__':
    raise SystemExit(main())
