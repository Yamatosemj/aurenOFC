from core.browser_verification import verificar_resultado_navegador


def _contexto(pagina):
    return {
        "abas": (
            "Abas abertas: 1\n"
            "Aba ativa: 1\n"
            "Aba 1: Editor | https://example.com [ATIVA]"
        ),
        "pagina": pagina,
    }


def test_fill_verification_accepts_matching_visible_value():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Nome","texto":"Victor","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | role=textbox | nome=Nome | valor=Victor"
        ),
    ) is True


def test_fill_verification_rejects_wrong_visible_value():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Nome","texto":"Victor","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | role=textbox | nome=Nome | valor=Maria"
        ),
    ) is False


def test_fill_verification_does_not_infer_redacted_secret():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Senha","texto":"segredo","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | nome=Senha | valor=[REDACTED]"
        ),
    ) is None

def test_click_element_uses_the_new_tab_as_active_page(monkeypatch):
    class _Page:
        def __init__(self, url):
            self.url = url

        def wait_for_timeout(self, _milliseconds):
            return None

    class _Element:
        def click(self, timeout):
            assert timeout == 10000

        def evaluate(self, _script):
            return "a"

        def get_attribute(self, _name):
            return "https://example.com/nova"

    antiga = _Page("https://example.com")
    nova = _Page("https://example.com/nova")
    elemento = _Element()

    import tools.browser as browser
    import tools.browser_elements as browser_elements

    monkeypatch.setattr(browser_elements, "encontrar_elemento", lambda alvo, indice=1: elemento)
    monkeypatch.setattr(browser, "obter_pagina", lambda: antiga)
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [antiga, nova])
    monkeypatch.setattr(browser, "pagina", antiga, raising=False)

    result = browser_elements.clicar_elemento("Abrir")

    assert "URL anterior: https://example.com" in result
    assert "URL atual: https://example.com/nova" in result
    assert "Navegacao: sim" in result
    assert browser.pagina is nova
