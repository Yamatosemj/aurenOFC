from __future__ import annotations

from tools import browser


class _FakePage:
    def __init__(self, url: str, title: str):
        self.url = url
        self._title = title
        self.closed = False

    def title(self):
        return self._title

    def is_closed(self):
        return self.closed

    def goto(self, url, wait_until=None, timeout=None):
        del wait_until, timeout
        self.url = url

    def bring_to_front(self):
        pass

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, pages):
        self.pages = pages

    def new_page(self):
        page = _FakePage("about:blank", "[sem titulo]")
        self.pages.append(page)
        return page


def test_open_new_tab_returns_structured_before_after_evidence(monkeypatch):
    existing = _FakePage("https://example.com", "Inicio")
    context = _FakeContext([existing])
    monkeypatch.setattr(browser, "browser_context", context)
    monkeypatch.setattr(browser, "modo_navegador", "visivel")
    monkeypatch.setattr(browser, "pagina", existing)
    monkeypatch.setattr(
        browser,
        "_paginas_abertas",
        lambda: [page for page in context.pages if not page.closed],
    )

    result = browser.abrir_nova_aba("https://example.com/novo")

    assert result.ok is True
    assert result.tool_name == "abrir_nova_aba"
    assert result.data["abas"]["quantidade_antes"] == 1
    assert result.data["abas"]["quantidade_depois"] == 2
    assert result.data["abas"]["aba_ativa_depois"] == 2
    assert result.data["abas"]["url_ativa_depois"] == "https://example.com/novo"


def test_switch_tab_returns_structured_active_state(monkeypatch):
    first = _FakePage("https://example.com", "Inicio")
    second = _FakePage("https://example.com/editor", "Editor")
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [first, second])
    monkeypatch.setattr(browser, "pagina", first)

    result = browser.trocar_aba(2)

    assert result.ok is True
    assert result.tool_name == "trocar_aba"
    assert result.data["abas"]["quantidade_antes"] == 2
    assert result.data["abas"]["quantidade_depois"] == 2
    assert result.data["abas"]["aba_ativa_depois"] == 2
    assert result.data["abas"]["url_ativa_depois"] == "https://example.com/editor"
    assert browser.pagina is second


def test_close_tab_returns_structured_before_after_evidence(monkeypatch):
    first = _FakePage("https://example.com", "Inicio")
    second = _FakePage("https://example.com/help", "Ajuda")
    pages = [first, second]
    monkeypatch.setattr(
        browser,
        "_paginas_abertas",
        lambda: [page for page in pages if not page.closed],
    )
    monkeypatch.setattr(browser, "pagina", second)

    result = browser.fechar_aba(2)

    assert result.ok is True
    assert result.tool_name == "fechar_aba"
    assert result.data["abas"]["quantidade_antes"] == 2
    assert result.data["abas"]["quantidade_depois"] == 1
    assert result.data["abas"]["aba_fechada"] == 2
    assert result.data["abas"]["aba_ativa_depois"] == 1
    assert result.data["abas"]["url_ativa_depois"] == "https://example.com"
    assert browser.pagina is first



def test_obter_pagina_does_not_restart_on_transient_context_read_error(monkeypatch):
    class _BrokenContext:
        @property
        def pages(self):
            raise RuntimeError("consulta temporariamente indisponivel")

    sentinel = object()
    monkeypatch.setattr(browser, "playwright", sentinel)
    monkeypatch.setattr(browser, "browser_context", _BrokenContext())
    monkeypatch.setattr(browser, "pagina", None)
    monkeypatch.setattr(
        browser,
        "reiniciar_navegador",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("falha transitória nao deve destruir a sessao")
        ),
    )

    try:
        browser.obter_pagina()
    except RuntimeError as erro:
        assert "consulta temporariamente indisponivel" in str(erro)
    else:
        raise AssertionError("obter_pagina deveria propagar a falha sem reiniciar")


def test_obter_pagina_recreates_only_when_context_is_confirmed_closed(monkeypatch):
    class _ClosedContext:
        def is_closed(self):
            return True

    replacement = object()
    chamadas = []
    monkeypatch.setattr(browser, "playwright", object())
    monkeypatch.setattr(browser, "browser_context", _ClosedContext())
    monkeypatch.setattr(browser, "pagina", None)
    monkeypatch.setattr(
        browser,
        "_abrir_contexto",
        lambda modo: chamadas.append(modo) or replacement,
    )

    assert browser.obter_pagina() is replacement
    assert chamadas == ["visivel"]


def test_obter_pagina_does_not_restart_when_new_page_fails(monkeypatch):
    class _Context:
        pages = []

        def new_page(self):
            raise RuntimeError("limite temporario do contexto")

    monkeypatch.setattr(browser, "playwright", object())
    monkeypatch.setattr(browser, "browser_context", _Context())
    monkeypatch.setattr(browser, "pagina", None)
    monkeypatch.setattr(
        browser,
        "reiniciar_navegador",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("falha ao criar aba nao deve reiniciar o perfil inteiro")
        ),
    )

    try:
        browser.obter_pagina()
    except RuntimeError as erro:
        assert "limite temporario do contexto" in str(erro)
    else:
        raise AssertionError("obter_pagina deveria propagar a falha de new_page")


def test_estado_abas_detects_external_real_focus_instead_of_internal_reference(monkeypatch):
    class _FocusedPage(_FakePage):
        def __init__(self, url, title, focused):
            super().__init__(url, title)
            self.focused = focused

        def evaluate(self, _script):
            return self.focused

        def bring_to_front(self):
            self.focused = True

    first = _FocusedPage("https://example.com", "Inicio", False)
    second = _FocusedPage("https://example.com/editor", "Editor", True)
    pages = [first, second]
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: pages)
    monkeypatch.setattr(browser, "pagina", first)

    estado = browser._estado_abas()

    assert "Aba ativa: 2" in estado
    assert "Aba 2: Editor | https://example.com/editor [ATIVA]" in estado
    assert "Aba 1: Inicio | https://example.com" in estado


def test_estado_abas_does_not_invent_active_tab_when_focus_is_ambiguous(monkeypatch):
    class _UnclearPage(_FakePage):
        def evaluate(self, _script):
            raise RuntimeError("foco indisponivel")

    first = _UnclearPage("https://example.com", "Inicio")
    second = _UnclearPage("https://example.com/editor", "Editor")
    pages = [first, second]
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: pages)
    monkeypatch.setattr(browser, "pagina", first)

    estado = browser._estado_abas()

    assert "Aba ativa: ?" in estado
    assert "[ATIVA]" not in estado


def test_trocar_aba_brings_selected_page_to_front(monkeypatch):
    class _FrontPage(_FakePage):
        def __init__(self, url, title):
            super().__init__(url, title)
            self.brought_to_front = 0

        def bring_to_front(self):
            self.brought_to_front += 1

    first = _FrontPage("https://example.com", "Inicio")
    second = _FrontPage("https://example.com/editor", "Editor")
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [first, second])
    monkeypatch.setattr(browser, "pagina", first)

    result = browser.trocar_aba(2)

    assert result.ok is True
    assert second.brought_to_front == 1
    assert browser.pagina is second

def test_navegar_navegador_does_not_restart_on_transient_goto_error(monkeypatch):
    class _Page:
        url = "https://example.com"

        def goto(self, *args, **kwargs):
            raise RuntimeError("falha transitoria de rede")

        def is_closed(self):
            return False

    monkeypatch.setattr(browser, "browser_context", object())
    monkeypatch.setattr(browser, "modo_navegador", "visivel")
    monkeypatch.setattr(browser, "obter_pagina", lambda: _Page())
    monkeypatch.setattr(
        browser,
        "reiniciar_navegador",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("falha transitória não deve reiniciar a sessão")
        ),
    )

    resultado = browser.navegar_navegador("https://example.com")

    assert resultado.ok is False
    assert "falha transitoria de rede" in resultado.message


def test_navegar_navegador_restarts_only_after_confirmed_page_closure(monkeypatch):
    class _ClosedPage:
        url = "https://example.com"

        def goto(self, *args, **kwargs):
            raise RuntimeError("pagina fechada")

        def is_closed(self):
            return True

    class _ReplacementPage:
        url = "https://example.com/novo"

        def goto(self, *args, **kwargs):
            self.url = args[0]

        def is_closed(self):
            return False

    replacement = _ReplacementPage()
    calls = []

    monkeypatch.setattr(browser, "browser_context", object())
    monkeypatch.setattr(browser, "modo_navegador", "visivel")
    monkeypatch.setattr(browser, "obter_pagina", lambda: _ClosedPage())
    monkeypatch.setattr(
        browser,
        "reiniciar_navegador",
        lambda *_args, **_kwargs: calls.append("restart") or replacement,
    )

    resultado = browser.navegar_navegador("https://example.com/novo")

    assert calls == ["restart"]
    assert resultado.ok is True
    assert resultado.data["navegacao"]["url_depois"] == "https://example.com/novo"


def test_listar_abas_returns_structured_snapshot(monkeypatch):
    page = _FakePage("https://example.com", "Inicio")
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [page])
    monkeypatch.setattr(browser, "pagina", page)

    result = browser.listar_abas()

    assert result.ok is True
    assert result.tool_name == "listar_abas"
    assert result.data["abas"]


def test_fechar_aba_empty_browser_is_structured_failure(monkeypatch):
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [])

    result = browser.fechar_aba()

    assert result.ok is False
    assert result.error_code == "no_open_tabs"


def test_fechar_aba_rejects_invalid_index_as_structured_failure(monkeypatch):
    page = _FakePage("https://example.com", "Inicio")
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [page])

    result = browser.fechar_aba("abc")

    assert result.ok is False
    assert result.error_code == "invalid_tab_index"
