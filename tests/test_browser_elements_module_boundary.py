import inspect

import tools.browser as browser
import tools.browser_elements as browser_elements


def test_browser_element_interactions_live_in_dedicated_module():
    public_names = (
        "encontrar_elemento",
        "clicar_elemento",
        "preencher_elemento",
    )

    for name in public_names:
        assert getattr(browser, name) is getattr(browser_elements, name)
        assert getattr(browser, name).__module__ == "tools.browser_elements"


def test_browser_element_module_preserves_nested_element_helpers():
    source = inspect.getsource(browser_elements.encontrar_elemento)
    assert "def visiveis(" in source
    assert "def procurar_atributo(" in source


def test_click_result_exposes_structured_navigation_evidence(monkeypatch):
    class _Page:
        def __init__(self, url):
            self.url = url

        def wait_for_timeout(self, _milliseconds):
            return None

        def title(self):
            return "Destino"

    class _Element:
        def evaluate(self, _script):
            return "a"

        def get_attribute(self, _name):
            return "https://example.com/destino"

        def click(self, timeout):
            assert timeout == 10000

    import tools.browser as browser

    antiga = _Page("https://example.com/origem")
    nova = _Page("https://example.com/destino")
    monkeypatch.setattr(browser_elements, "encontrar_elemento", lambda alvo, indice=1: _Element())
    monkeypatch.setattr(browser, "obter_pagina", lambda: antiga)
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [antiga, nova])
    monkeypatch.setattr(browser, "pagina", antiga, raising=False)

    result = browser_elements.clicar_elemento("Destino")

    assert result.ok is True
    assert result.tool_name == "clicar_elemento"
    assert result.data["clique"]["href"] == "https://example.com/destino"
    assert result.data["clique"]["url_anterior"] == "https://example.com/origem"
    assert result.data["clique"]["url_atual"] == "https://example.com/destino"
    assert result.data["clique"]["navegacao"] is True
    assert result.data["clique"]["nova_aba"] is True