"""Real isolated Chromium and DOM, all page requests intercepted offline."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from core.permission_manager import PermissionManager
from core.browser_verification import verificar_resultado_navegador
from tools import browser, dispatcher


def test_search_fixture_with_real_browser_dom_and_dispatcher(tmp_path, monkeypatch):
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        executable = Path(pw.chromium.executable_path)
        if not executable.is_file():
            pytest.skip('Chromium cache unavailable; no download permitted')
        try:
            context = pw.chromium.launch_persistent_context(str(tmp_path/'isolated-browser'),
                executable_path=str(executable), headless=True,
                args=['--disable-background-networking', '--disable-component-update', '--no-first-run',
                      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost'])
        except api.Error as exc:
            if 'Access is denied' in str(exc) or 'Acesso negado' in str(exc):
                pytest.skip('Environment denies isolated Chromium process creation')
            raise
        try:
            url = 'http://127.0.0.1/auren-fixture/search?q=teste'
            context.route('**/*', lambda route: route.fulfill(status=200,
                content_type='text/html', body='<title>Pesquisa ficticia</title><h1>Resultado Ficticio 17</h1>')
                if route.request.url == url else route.abort())
            for name, value in {'playwright': pw, 'browser_context': context,
                                'pagina': context.pages[0], 'modo_navegador': 'oculto'}.items():
                monkeypatch.setattr(browser, name, value)
            pm = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: False))
            def execute(name, args):
                return dispatcher.executar_ferramenta(SimpleNamespace(name=name, arguments=json.dumps(args)), pm, None)
            navigate = execute('navegar_navegador', {'url': url, 'modo': 'oculto'})
            assert navigate.ok
            read = execute('obter_contexto_navegador', {'foco': 'Resultado'})
            assert read.ok and read.conteudo_nao_confiavel
            assert 'Resultado Ficticio 17' in read.message
            assert verificar_resultado_navegador('navegar_navegador', json.dumps({'url': url}), read.data) is True
        finally:
            context.close()
