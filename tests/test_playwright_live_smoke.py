from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_real_playwright_browser_wrapper_smoke():
    script = r'''
from playwright.sync_api import sync_playwright
from tools import browser
from tools import browser_context as browser_context_tool
from core.browser_verification import verificar_resultado_navegador

with sync_playwright() as playwright:
    real_browser = playwright.chromium.launch(headless=True)
    context = real_browser.new_context()
    page = context.new_page()
    page.set_content("""
        <html>
          <body>
            <button id="menu" aria-expanded="false" onclick="this.setAttribute('aria-expanded', 'true')">Menu</button>
            <input id="nome" aria-label="Nome" />
            <details id="ajuda"><summary>Ajuda</summary><p>Detalhes</p></details>
          </body>
        </html>
    """)

    browser.playwright = playwright
    browser.browser = real_browser
    browser.browser_context = context
    browser.pagina = page
    browser.modo_navegador = "visivel"

    click = browser.clicar_elemento("Menu", 1)
    assert click.ok is True
    assert click.data["clique"]["navegacao"] is False

    contexto = browser.ler_pagina("Menu")
    assert "aria-expanded=true" in contexto.message

    contexto_real = browser_context_tool.obter_contexto_navegador("")
    assert contexto_real.ok is True
    verificado = verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        contexto_real.data,
        click.data,
    )
    assert verificado is True

    page.locator("#menu").click()
    contexto_invalido = browser.ler_pagina("Menu")
    assert contexto_invalido.ok is True
    dados_contexto_invalido = {
        "abas": contexto_real.data["abas"],
        "pagina": contexto_invalido.message,
    }
    falha_detectada = verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        dados_contexto_invalido,
        click.data,
    )
    assert falha_detectada is False

    preenchimento = browser.preencher_elemento("Nome", "Victor", 1)
    assert preenchimento.ok is True

    leitura = browser.ler_pagina("Nome")
    assert "valor=Victor" in leitura.message

    page.locator("#ajuda summary").click()
    leitura_details = browser.ler_pagina("Ajuda")
    assert "details-open=true" in leitura_details.message

    context.close()
    real_browser.close()
'''
    env = dict(os.environ)
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
