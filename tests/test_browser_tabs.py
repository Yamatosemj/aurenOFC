from __future__ import annotations

from tools import browser


class _FakePage:
    def __init__(self, url: str, title: str):
        self.url = url
        self._title = title
        self.closed = False

    def title(self):
        return self._title

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
