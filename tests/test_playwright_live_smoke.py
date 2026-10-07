from __future__ import annotations

from playwright.sync_api import sync_playwright

from tools import browser


def test_real_playwright_browser_wrapper_smoke(monkeypatch):
    with sync_playwright() as playwright:
        real_browser = playwright.chromium.launch(headless=True)
        context = real_browser.new_context()
        page = context.new_page()
        page.set_content(
            """
            <html>
              <body>
                <button id="menu" aria-expanded="false" onclick="this.setAttribute('aria-expanded', 'true')">Menu</button>
                <input id="nome" aria-label="Nome" />
                <details id="ajuda"><summary>Ajuda</summary><p>Detalhes</p></details>
              </body>
            </html>
            """
        )

        monkeypatch.setattr(browser, "playwright", playwright)
        monkeypatch.setattr(browser, "browser", real_browser)
        monkeypatch.setattr(browser, "browser_context", context)
        monkeypatch.setattr(browser, "pagina", page)
        monkeypatch.setattr(browser, "modo_navegador", "visivel")

        click = browser.clicar_elemento("Menu", 1)
        assert click.ok is True
        assert click.data["clique"]["navegacao"] is False

        contexto = browser.ler_pagina("Menu")
        assert "aria-expanded=true" in contexto

        preenchimento = browser.preencher_elemento("Nome", "Victor", 1)
        assert preenchimento.ok is True

        leitura = browser.ler_pagina("Nome")
        assert "valor=Victor" in leitura

        page.locator("#ajuda summary").click()
        leitura_details = browser.ler_pagina("Ajuda")
        assert "details-open=true" in leitura_details

        context.close()
        real_browser.close()
