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
        antes = float(p.evaluate("window.scrollY || 0") or 0)

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

        depois = float(p.evaluate("window.scrollY || 0") or 0)
        altura_documento = float(
            p.evaluate(
                "Math.max(document.body?.scrollHeight || 0, "
                "document.documentElement?.scrollHeight || 0)"
            ) or 0
        )
        altura_viewport = float(p.evaluate("window.innerHeight || 0") or 0)

        return ToolResult.success(
            f"Pagina rolada para '{direcao}'.",
            data={
                "direcao": str(direcao),
                "scroll_y_antes": antes,
                "scroll_y_depois": depois,
                "scroll_height": altura_documento,
                "viewport_height": altura_viewport,
            },
            tool_name="rolar_pagina",
        )

    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui rolar a pagina: {erro}",
            error_code="scroll_failed",
            tool_name="rolar_pagina",
        )

