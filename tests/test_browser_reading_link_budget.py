"""A leitura operacional deve preservar links verificáveis sob seu próprio limite."""

from core.browser_verification import contexto_resultados
from tools import browser, browser_reading


def test_search_links_survive_verbose_snippets_and_controls(monkeypatch):
    search = 'https://www.google.com/search?q=create+aeronautics'
    result = 'https://modrinth.test/mod/create-aeronautics'
    abas = f'Aba ativa: 1\nAba 1: Busca | {search} [ATIVA]'

    class Page:
        url = search

        def title(self):
            return 'Busca'

        def evaluate(self, _script, _args):
            return {
                'resultadosEstruturados': [],
                'snippets': [{'texto': 'resultado ' + 's' * 245}] * 7,
                'controles': [{'tag': 'button', 'nome': 'c' * 300}] * 10,
                'links': [{'texto': 'Create Aeronautics - Minecraft Mods',
                           'href': result}],
                'candidatosOrdem': [{'texto': 'Create Aeronautics - Minecraft Mods',
                                     'href': result}],
            }

        def wait_for_load_state(self, *_args, **_kwargs):
            pass

        def wait_for_timeout(self, *_args):
            pass

    monkeypatch.setattr(browser, 'obter_pagina', lambda: Page())
    monkeypatch.setattr(browser, '_estado_abas', lambda: abas)
    pagina = browser_reading.ler_pagina('resultados')
    assert result in [item['url'] for item in contexto_resultados({
        'abas': abas, 'pagina': pagina,
    })['links']]
