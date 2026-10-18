"""Explicit isolated UI check. Fake provider/effects; no positive confirmation."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from threading import Event, Thread
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

from agent.planner import PlanBuilder
from core.harness import AurenHarness
from core.permission_manager import PermissionManager, PermissionLevel
from core.task_manager import TaskManager, TaskState
from core.tool_result import ToolResult
from tools import dispatcher
from ui.backend import AurenUiWorker
from ui.chrome_server import ChromeServer, LocalChromeApp


def seed(db, objective):
    manager=TaskManager(db_path=db)
    manager.create(objective, chat_id='fixture-owner', plan=PlanBuilder.build(objective))
    manager.start()
    manager.configure_model_budget(8)
    manager.begin_step('obter_audio_windows')
    manager.finish_step(success=True, result='Volume ficticio:20')
    manager.save_execution_checkpoint(PermissionManager().checkpoint_limits())
    manager.pause()
    manager.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True)
    args=parser.parse_args()
    output=Path(args.artifacts).resolve()
    output.mkdir(parents=True, exist_ok=False)
    db=output/'browser.sqlite3'
    objective='Qual o volume atual? <img src=x onerror="window.fixtureInjected=true">'
    seed(db, objective)
    checks=[]
    def record(name):
        checks.append(name)
        (output/'progress.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    effects=[]
    model_calls=[]
    blocked_requests=[]
    page_errors=[]
    entered,release=Event(),Event()
    def factory(confirmation_channel):
        pm=PermissionManager(confirmation_channel=confirmation_channel)
        pm.policy['windows.audio.control']=PermissionLevel.CONFIRM
        def model(*_):
            task=harness.current_task()
            model_calls.append(task.objective)
            if task.objective.startswith('Defina') and not task.steps:
                item=SimpleNamespace(type='function_call', name='definir_volume_windows',
                    arguments='{"percentual":35}',call_id='volume')
                return SimpleNamespace(output=[item],output_text='',usage=None)
            if task.objective.startswith('Consulte') and not task.steps:
                entered.set()
                assert release.wait(15)
                item=SimpleNamespace(type='function_call',name='obter_audio_windows',arguments='{}',call_id='read')
                return SimpleNamespace(output=[item],output_text='',usage=None)
            return SimpleNamespace(output=[],output_text='Resultado ficticio observado.',usage=None)
        harness=AurenHarness(task_manager=TaskManager(db_path=db),permission_manager=pm,
            criar_resposta=model,obter_chamadas=lambda r:r.output,
            executar_ferramenta=lambda call:dispatcher.executar_ferramenta(call,pm,None),
            mostrar_uso=lambda:None,comando_rapido=lambda _:(False,''),iniciar_tarefa=pm.iniciar_tarefa,
            apos_tarefa=None,fechar=lambda:None)
        return harness
    dispatcher.TOOL_HANDLERS['definir_volume_windows']=lambda *_:effects.append('must-not-run') or ToolResult.success('fixture')
    dispatcher.TOOL_HANDLERS['obter_audio_windows']=lambda *_:ToolResult.success('Volume ficticio:20')
    worker=AurenUiWorker(harness_factory=factory)
    app=LocalChromeApp(worker)
    server=ChromeServer(app)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        from playwright.sync_api import sync_playwright,expect
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,chromium_sandbox=True,
                args=['--disable-background-networking','--disable-component-update'])
            browser_version=browser.version
            context=browser.new_context(viewport={'width':1365,'height':900},service_workers='block')
            origin=f'http://127.0.0.1:{server.server_port}'
            def route(request):
                if request.request.url.startswith(origin+'/'):
                    request.continue_()
                else:
                    blocked_requests.append(urlsplit(request.request.url).scheme)
                    request.abort()
            context.route('**/*',route)
            page=context.new_page()
            page.set_default_timeout(15000)
            page.on('pageerror',lambda error:page_errors.append(str(error)))
            page.goto(origin)
            page.locator('#taskPanel > summary').click()
            page.get_by_role('button',name='Carregar histórico',exact=True).click()
            expect(page.locator('#taskChat option[value="fixture-owner"]')).to_have_count(1)
            page.locator('#taskChat').select_option('fixture-owner')
            card=page.locator('#taskList article').filter(has_text=objective)
            expect(card).to_contain_text('Pausada')
            assert card.locator('img').count()==0 and page.evaluate('window.fixtureInjected===true') is False
            record('saved_goal_shown_as_text_without_html_execution')
            card.get_by_role('button',name='Retomar',exact=True).click()
            expect(card).to_contain_text('Concluída')
            assert len(worker._harness.current_task().steps)==1
            record('same_goal_resumed_without_repeating_saved_step')
            page.locator('#taskPanel > details > summary').click()
            page.locator('#routineGoal').fill('Conferir relatorio ficticio')
            now=time.time()
            page.locator('#routineDue').fill(datetime.fromtimestamp(now+3600).strftime('%Y-%m-%dT%H:%M'))
            page.locator('#routineExpiry').fill(datetime.fromtimestamp(now+7200).strftime('%Y-%m-%dT%H:%M'))
            page.get_by_role('button',name='Salvar rascunho',exact=True).click()
            routine=page.locator('#routineList article').filter(has_text='Conferir relatorio ficticio')
            expect(routine).to_contain_text('Rascunho')
            assert worker.task_dashboard()['routines'][0]['status']=='draft'
            routine.get_by_role('button',name='Revogar',exact=True).click()
            expect(routine).to_contain_text('Revogada')
            record('routine_draft_not_auto_authorized_and_revoked')
            page.locator('#taskPanel > details > summary').click()
            page.locator('#c').click(position={'x':400,'y':300})
            page.locator('#msg').fill('Defina o volume para 35.')
            page.locator('#msg').press('Enter')
            expect(page.locator('#authPanel')).to_be_visible()
            page.get_by_role('button',name='Negar',exact=True).click()
            denied=page.locator('#taskList article').filter(has_text='Defina o volume para 35.')
            expect(denied).to_contain_text('Falhou')
            assert effects==[]
            record('real_confirmation_ui_denied_without_running_handler')
            page.locator('#c').click(position={'x':400,'y':300})
            pause_objective='Consulte o volume e depois consulte o status.'
            page.locator('#msg').fill(pause_objective)
            page.locator('#msg').press('Enter')
            paused=page.locator('#taskList article').filter(has_text=pause_objective)
            expect(paused).to_contain_text('Aguardando modelo')
            paused.get_by_role('button',name='Pausar',exact=True).click()
            expect(page.locator('#taskHint')).to_contain_text('Pausa solicitada')
            release.set()
            expect(paused).to_contain_text('Pausada')
            assert worker._harness.current_task().state is TaskState.PAUSED
            record('live_waiting_progress_and_cooperative_pause_persisted')
            page.screenshot(path=str(output/'chrome.png'),full_page=True)
            assert page_errors==[],page_errors
            record('page_javascript_has_no_runtime_errors')
            context.close()
            browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        app.shutdown()
        worker._thread.join(5)
        thread.join(3)
    assert not worker.alive
    manager=TaskManager(db_path=db)
    assert manager.current_snapshot().state is TaskState.PAUSED
    assert manager.current_snapshot().cancel_requested is False
    manager.close()
    record('browser_worker_closed_and_database_reopened_with_pause_intact')
    import tkinter as tk
    from interface_auren import AurenDesktop
    tk_db=output/'tk.sqlite3'
    seed(tk_db,'Qual o volume ficticio?')
    def tk_factory(confirmation_channel):
        return AurenHarness(task_manager=TaskManager(db_path=tk_db),
            criar_resposta=lambda *_:(_ for _ in ()).throw(AssertionError('No model call in Tk test')),
            obter_chamadas=lambda r:r.output,executar_ferramenta=lambda _:None,
            mostrar_uso=lambda:None,comando_rapido=lambda _:(False,''),
            iniciar_tarefa=lambda:None,apos_tarefa=None,fechar=lambda:None)
    root=tk.Tk()
    root.withdraw()
    tk_worker=AurenUiWorker(harness_factory=tk_factory)
    desktop=AurenDesktop(root,tk_worker)
    try:
        desktop._load_tasks()
        deadline=time.monotonic()+5
        while not tk_worker.task_dashboard()['chats'] and time.monotonic()<deadline:
            root.update()
            time.sleep(.01)
        assert tk_worker.task_action('select',chat_id='fixture-owner',generation=tk_worker.generation)
        deadline=time.monotonic()+5
        while tk_worker.task_dashboard()['chat_id']!='fixture-owner' and time.monotonic()<deadline:
            root.update()
            time.sleep(.01)
        desktop._refresh_tasks()
        rows=desktop.task_rows.get_children()
        assert len(rows)==1 and desktop.task_rows.item(rows[0])['values'][1]=='Pausada'
        desktop.task_rows.selection_set(rows[0])
        desktop._task_control('cancel')
        assert tk_worker._harness.task_manager.get_snapshot(rows[0]).state is TaskState.CANCELLED
        record('real_tk_widgets_show_saved_pause_and_cancel_it')
    finally:
        tk_worker.close()
        tk_worker._thread.join(5)
        root.destroy()
    assert not tk_worker.alive
    result={'checks':checks,'passed':len(checks),'failed':0,'chrome_version':browser_version,
        'model':'scripted fake; no API','personal_effects':effects,'model_calls':len(model_calls),
        'external_page_requests_aborted':len(blocked_requests),'page_errors':page_errors,
        'screenshot':'chrome.png','tk':'real widgets with root withdrawn; no physical appearance validation'}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
