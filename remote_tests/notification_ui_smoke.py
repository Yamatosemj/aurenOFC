"""Explicit offline Chromium check: real UI/HTTP/SQLite, fake time, no API."""
import argparse
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
import time
from types import SimpleNamespace

from core.harness import AurenHarness
from core.harness_runtime import SessionContext
from core.routines import RoutineScheduler
from core.task_manager import TaskManager, TaskState
from ui.backend import AurenUiWorker
from ui.chrome_server import ChromeServer, LocalChromeApp


def wait_for(predicate, page):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if predicate():
            return
        # Pump Playwright's sync dispatcher so intercepted ACK requests run.
        page.wait_for_timeout(20)
    raise AssertionError('Fixture condition not reached')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True)
    output = Path(parser.parse_args().artifacts).resolve()
    output.mkdir(parents=True, exist_ok=False)
    db, now = output/'tasks.sqlite3', [100]
    checks, errors, external = [], [], []
    def record(name):
        checks.append(name)
        (output/'progress.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')

    def start():
        manager = TaskManager(db_path=db)
        h = AurenHarness(task_manager=manager,
            criar_resposta=lambda *a, **k: (_ for _ in ()).throw(AssertionError('No API in UI test')),
            executar_ferramenta=lambda c: (_ for _ in ()).throw(AssertionError('No tool effects')),
            obter_chamadas=lambda r: r.output, mostrar_uso=lambda: None,
            comando_rapido=lambda _: (False, ''), iniciar_tarefa=lambda: None,
            apos_tarefa=None, fechar=lambda: None)
        h._session = SessionContext('fixture-owner', output/'chat.log')
        worker = AurenUiWorker()
        worker._harness = h
        worker._scheduler = RoutineScheduler(manager, clock=lambda: now[0])
        # This browser fixture drives tick explicitly with the controlled clock.
        # Production worker polling is covered by integration_fixture/routines.
        worker._poll_routines = lambda: None
        worker.activate()
        app = LocalChromeApp(worker)
        app.mode = 'active'
        server = ChromeServer(app)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return app, worker, server, thread

    def stop(bundle):
        app, worker, server, thread = bundle
        server.shutdown()
        server.server_close()
        app.shutdown()
        worker._thread.join(5)
        thread.join(3)
        assert not worker.alive

    bundle = start()
    try:
        app, worker, server, _ = bundle
        scheduler = worker._scheduler
        text = 'ESTUDAR_FICTICIO <img src=x onerror="window.fixtureInjected=true">'
        r = scheduler.register(chat_id='fixture-owner', objective=text, due_at=100, expires_at=1000)
        scheduler.authorize(r['id'], chat_id='fixture-owner')
        scheduler.tick(None, chat_id='fixture-owner')
        notice = scheduler.pending_notifications(chat_id='fixture-owner')[0]
        # This event was never sent to the worker queue; delivery must come from SQLite.
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, chromium_sandbox=True,
                args=['--disable-background-networking', '--disable-component-update'])
            context = browser.new_context(viewport={'width': 1200, 'height': 900}, service_workers='block')
            block_ack = [True]
            def route(request):
                url = request.request.url
                if not url.startswith(f'http://127.0.0.1:{server.server_port}/'):
                    external.append(url.split(':')[0])
                    request.abort()
                elif url.endswith('/api/notification-action') and block_ack[0]:
                    request.abort()
                else:
                    request.continue_()
            context.route('**/*', route)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.set_default_timeout(10000)
            page.goto(f'http://127.0.0.1:{server.server_port}')
            card = page.locator('#routineNotices article')
            expect(card).to_be_visible()
            expect(card).to_contain_text(text)
            assert card.locator('img').count() == 0
            assert page.evaluate('window.fixtureInjected===true') is False
            assert scheduler.pending_notifications(chat_id='fixture-owner') == [notice]
            record('visible_card_from_persisted_notice_without_html_execution')
            page.reload()
            expect(card).to_be_visible()
            assert scheduler.pending_notifications(chat_id='fixture-owner') == [notice]
            record('failed_ack_and_reload_do_not_lose_notice')
            block_ack[0] = False
            wait_for(lambda: scheduler.pending_notifications(chat_id='fixture-owner') == [], page)
            expect(card).to_be_visible()
            record('browser_confirms_only_after_visible_render')
            app.change_mode('standby')
            expect(page.locator('#bEstados')).to_contain_text('Standby')
            expect(card).to_be_visible()
            card.get_by_role('button', name='Adiar aviso 10 min', exact=True).click()
            expect(card).to_have_count(0)
            assert scheduler.pending_notifications(chat_id='fixture-owner') == []
            assert scheduler.get(r['id'], chat_id='fixture-owner')['runs_left'] == 0
            record('standby_snooze_hides_card_without_reenabling_routine')
            context.close()
            stop(bundle)
            bundle = None
            now[0] = 699
            bundle = start()
            app, worker, server, _ = bundle
            scheduler = worker._scheduler
            assert scheduler.pending_notifications(chat_id='fixture-owner') == []
            context = browser.new_context(viewport={'width': 1200, 'height': 900}, service_workers='block')
            context.route('**/*', route)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            expect(page.locator('#routineNotices article')).to_have_count(0)
            now[0] = 700
            expect(page.locator('#routineNotices article')).to_be_visible()
            expect(page.locator('#routineNotices article')).to_have_attribute('data-revision', '2')
            wait_for(lambda: scheduler.pending_notifications(chat_id='fixture-owner') == [], page)
            assert scheduler.tick(None, chat_id='fixture-owner') == []
            assert scheduler.get(r['id'], chat_id='fixture-owner')['runs_left'] == 0
            record('snooze_survives_worker_server_restart_and_is_delivered_at_new_time')
            uncertain = scheduler.register(chat_id='fixture-owner', objective='LEITURA_NAO_COMPROVADA',
                due_at=700, expires_at=1000, mode='execute',
                allowed_calls=[{'name':'obter_audio_windows','arguments':{}}], model_budget=1)
            scheduler.authorize(uncertain['id'], chat_id='fixture-owner')
            fake = SimpleNamespace(task_manager=scheduler.manager,
                _garantir_sessao_chat=lambda:'fixture-owner', processar_mensagem=lambda *a,**k:None,
                current_task=lambda:SimpleNamespace(task_id='fictitious',state=TaskState.COMPLETED,steps=[]))
            scheduler.tick(fake, chat_id='fixture-owner')
            expect(page.locator('#routineNotices article').filter(has_text='LEITURA_NAO_COMPROVADA')).to_contain_text('Resultado da rotina não comprovado')
            record('model_only_answer_is_shown_as_unverified_instead_of_success')
            page.screenshot(path=str(output/'notifications.png'), full_page=True)
            # Endpoint authentication remains mandatory, including for acknowledgements.
            conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            body = json.dumps({'action':'ack','id':notice['id'],'revision':2,
                'chat_id':'fixture-owner','generation':worker.generation})
            conn.request('POST', '/api/notification-action', body=body,
                headers={'Content-Type':'application/json'})
            response = conn.getresponse()
            assert response.status == 403
            response.read()
            conn.close()
            record('ack_endpoint_rejects_missing_session_token')
            assert not worker.notification_action('ack', notification_id=notice['id'], revision=2,
                chat_id='other', generation=worker.generation)
            app.change_mode('off')
            expect(page.locator('#routineNotices article')).to_have_count(0)
            assert not worker.notification_action('ack', notification_id=notice['id'], revision=2,
                chat_id='fixture-owner', generation=worker.generation-1)
            record('wrong_chat_and_off_session_cannot_acknowledge')
            assert errors == [], errors
            context.close()
            browser.close()
            record('no_javascript_errors_no_model_calls_no_tool_effects')
    finally:
        if bundle:
            stop(bundle)
    result = {'passed': len(checks), 'failed': 0, 'checks': checks,
        'api_calls': 0, 'tool_effects': 0, 'external_requests_blocked': len(external),
        'page_errors': errors, 'browser': 'real isolated Chromium headless',
        'clock': 'controlled; snooze advances from 100 to 700'}
    (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
