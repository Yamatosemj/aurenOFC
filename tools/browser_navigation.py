from __future__ import annotations

from core.tool_result import ToolResult


def pressionar_tecla(tecla):
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        p.keyboard.press(tecla)

        return f"Pressionei a tecla '{tecla}'."

    except Exception as erro:
        return (
            f"Nao consegui pressionar '{tecla}': {erro}"
        )

def voltar_pagina():
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        p.go_back(
            wait_until="domcontentloaded",
            timeout=12000
        )

        return (
            "Voltei para a pagina anterior.\n"
            f"URL atual: {p.url}"
        )

    except Exception as erro:
        return f"Nao consegui voltar: {erro}"

def avancar_pagina():
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        p.go_forward(
            wait_until="domcontentloaded",
            timeout=12000
        )

        return (
            "Avancei para a proxima pagina.\n"
            f"URL atual: {p.url}"
        )

    except Exception as erro:
        return f"Nao consegui avancar: {erro}"

def recarregar_pagina():
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        p.reload(
            wait_until="domcontentloaded",
            timeout=12000
        )

        return (
            "Pagina recarregada.\n"
            f"URL atual: {p.url}"
        )

    except Exception as erro:
        return f"Nao consegui recarregar: {erro}"

def rolar_pagina(direcao):
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()

        if direcao == "cima":
            p.mouse.wheel(0, -900)

        elif direcao == "baixo":
            p.mouse.wheel(0, 900)

        elif direcao == "inicio":
            p.evaluate("window.scrollTo(0, 0)")

        elif direcao == "fim":
            p.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            )

        else:
            return ToolResult.failure(
                "Direcao invalida. Use cima, baixo, inicio ou fim.",
                error_code="scroll_direction_invalid",
            )

        return f"Pagina rolada para '{direcao}'."

    except Exception as erro:
        return f"Nao consegui rolar a pagina: {erro}"

