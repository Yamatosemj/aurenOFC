from __future__ import annotations

from types import SimpleNamespace


def test_click_element_uses_new_tab_after_click(monkeypatch):
    import tools.browser as browser
    import tools.browser_elements as browser_elements

    antiga = SimpleNamespace(url="https://example.com")
    nova = SimpleNamespace(url="https://example.com/nova")
    paginas = [antiga]

    class FakeElement:
        def evaluate(self, _script):
            return "a"

        def get_attribute(self, name):
            if name == "href":
                return "https://example.com/nova"
            return ""

        def click(self, timeout):
            assert timeout == 10000
            paginas.append(nova)

    elemento = FakeElement()

    monkeypatch.setattr(browser_elements, "encontrar_elemento", lambda alvo, indice=1: elemento)
    monkeypatch.setattr(browser, "obter_pagina", lambda: antiga)
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: list(paginas))
    monkeypatch.setattr(browser, "pagina", antiga, raising=False)

    resultado = browser_elements.clicar_elemento("Abrir", 1)

    assert "URL anterior: https://example.com" in resultado.message
    assert "URL atual: https://example.com/nova" in resultado.message
    assert "Navegacao: sim" in resultado.message
    assert resultado.ok
    assert resultado.data["clique"]["nova_aba"] is True
    assert resultado.data["clique"]["url_depois"] == nova.url
    assert getattr(browser, "pagina") is nova
