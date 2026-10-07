from core.browser_verification import _compromisso_preenchimento_sensivel, verificar_resultado_navegador


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
            if nova not in paginas:
                paginas.append(nova)

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
    paginas = [antiga]
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: list(paginas))
    monkeypatch.setattr(browser, "pagina", antiga, raising=False)

    result = browser_elements.clicar_elemento("Abrir")

    assert result.ok is True
    assert result.data["clique"]["url_anterior"].endswith("/example.com")
    assert result.data["clique"]["url_atual"].endswith("/nova")
    assert result.data["clique"]["navegacao"] is True



def test_sensitive_fill_returns_redacted_verification_commitment():
    import tools.browser_elements as browser_elements

    class _SensitiveElement:
        def fill(self, value, timeout):
            assert value == "segredo-super-secreto"
            assert timeout == 10000

        def input_value(self, timeout=None):
            assert timeout == 10000
            return "segredo-super-secreto"

        def get_attribute(self, name):
            return {"type": "password"}.get(name)

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(browser_elements, "encontrar_elemento", lambda *args, **kwargs: _SensitiveElement())
        result = browser_elements.preencher_elemento("Senha", "segredo-super-secreto", 1)
    finally:
        monkeypatch.undo()

    assert result.ok is True
    evidence = result.data["preenchimento"]
    assert evidence["sensivel"] is True
    assert evidence["verificado_localmente"] is True
    assert evidence["compromisso"]
    assert "segredo-super-secreto" not in result.message
    assert "segredo-super-secreto" not in str(result.data)



def test_sensitive_fill_verification_matches_private_commitment_without_secret():
    compromisso = _compromisso_preenchimento_sensivel("segredo-super-secreto")
    pagina = (
        "Campos e controles visiveis:\n"
        f"- tag=input | nome=Senha | chave=aria:Senha | valor=[REDACTED] | compromisso={compromisso}"
    )

    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Senha","texto":"segredo-super-secreto","indice":1}',
        _contexto(pagina),
        {
            "preenchimento": {
                "alvo": "Senha",
                "indice": 1,
                "sensivel": True,
                "verificado_localmente": True,
                "compromisso": compromisso,
            }
        },
    ) is True


def test_sensitive_fill_verification_rejects_mismatched_commitment():
    pagina = (
        "Campos e controles visiveis:\n"
        "- tag=input | nome=Senha | chave=aria:Senha | valor=[REDACTED] | compromisso=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Senha","texto":"segredo-super-secreto","indice":1}',
        _contexto(pagina),
        {
            "preenchimento": {
                "alvo": "Senha",
                "indice": 1,
                "sensivel": True,
                "verificado_localmente": True,
                "compromisso": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        },
    ) is False


def test_browser_reader_exposes_commitment_but_never_sensitive_value(monkeypatch):
    from tools import browser
    from tools import browser_reading

    class FakePage:
        url = "https://example.com"

        def title(self):
            return "Teste"

        def evaluate(self, _script, *_args):
            return {
                "controles": [{
                    "score": 5,
                    "ordem": 0,
                    "tag": "input",
                    "role": "textbox",
                    "nome": "Senha",
                    "nameAttr": "senha",
                    "id": "senha",
                    "placeholder": "Senha",
                    "chave": "id:senha",
                    "estados": {},
                    "value": "[REDACTED]",
                    "valor_interno": "segredo-super-secreto",
                }],
                "elementosFlutuantes": {"dialogos": 0, "menus": 0, "listboxes": 0},
                "links": [],
                "candidatosOrdem": [],
                "resultadosEstruturados": [],
                "snippets": [],
            }

    monkeypatch.setattr(browser, "obter_pagina", lambda: FakePage())
    monkeypatch.setattr(browser, "_estado_abas", lambda: "Abas abertas: 1\\nAba ativa: 1\\nAba 1: Teste | https://example.com [ATIVA]")

    resultado = browser_reading.ler_pagina("senha")
    compromisso = _compromisso_preenchimento_sensivel("segredo-super-secreto")

    assert compromisso in resultado
    assert "[REDACTED]" in resultado
    assert "segredo-super-secreto" not in resultado
