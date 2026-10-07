from __future__ import annotations

from core.tool_result import ToolResult


def _instalar_probe_historico(p):
    try:
        p.evaluate(
            """() => {
                const antigo = window.__aurenHistoryProbeCleanup;
                if (typeof antigo === 'function') antigo();
                const estado = {popstate: 0, hashchange: 0};
                const popstate = () => { estado.popstate += 1; };
                const hashchange = () => { estado.hashchange += 1; };
                window.addEventListener('popstate', popstate, true);
                window.addEventListener('hashchange', hashchange, true);
                window.__aurenHistoryProbe = estado;
                window.__aurenHistoryProbeCleanup = () => {
                    window.removeEventListener('popstate', popstate, true);
                    window.removeEventListener('hashchange', hashchange, true);
                };
            }"""
        )
        return True
    except Exception:
        return False


def _ler_probe_historico(p):
    try:
        probe = p.evaluate("() => window.__aurenHistoryProbe || {popstate: 0, hashchange: 0}") or {}
        return isinstance(probe, dict) and (int(probe.get("popstate") or 0) + int(probe.get("hashchange") or 0) > 0)
    except Exception:
        return None
    finally:
        try:
            p.evaluate(
                """() => {
                    if (typeof window.__aurenHistoryProbeCleanup === 'function') window.__aurenHistoryProbeCleanup();
                    window.__aurenHistoryProbeCleanup = null;
                    window.__aurenHistoryProbe = null;
                }"""
            )
        except Exception:
            pass


def _snapshot_pagina(p):
    try:
        return p.evaluate(
            """() => ({
                url: location.href,
                titulo: document.title || '',
                scroll_y: Number(window.scrollY || 0),
                time_origin: Number(performance.timeOrigin || 0),
                dialogs: document.querySelectorAll('dialog, [role="dialog"], [role="alertdialog"]').length,
                menus: document.querySelectorAll('[role="menu"]').length,
                listboxes: document.querySelectorAll('[role="listbox"]').length,
                active: (() => {
                    const el = document.activeElement;
                    if (!el) return null;
                    return {
                        tag: el.tagName || '',
                        id: el.id || '',
                        name: el.getAttribute?.('name') || '',
                        role: el.getAttribute?.('role') || '',
                        aria_label: el.getAttribute?.('aria-label') || '',
                    };
                })(),
            })"""
        ) or {}
    except Exception:
        return {
            "url": str(getattr(p, "url", "") or ""),
            "titulo": "",
            "scroll_y": None,
            "time_origin": None,
            "dialogs": None,
            "menus": None,
            "listboxes": None,
            "active": None,
        }


def pressionar_tecla(tecla):
    from tools import browser as _browser

    try:
        tecla = str(tecla or "").strip()
        if not tecla:
            return ToolResult.failure(
                "Tecla vazia.",
                error_code="key_invalid",
                tool_name="pressionar_tecla",
            )
        p = _browser.obter_pagina()
        antes = _snapshot_pagina(p)
        abas_antes = _browser._abas_snapshot()

        p.evaluate(
            """() => {
                const antigo = window.__aurenKeyProbeCleanup;
                if (typeof antigo === 'function') antigo();
                const estado = { count: 0, key: '' };
                const handler = (event) => {
                    estado.count += 1;
                    estado.key = event.key || '';
                };
                window.__aurenKeyProbe = estado;
                window.__aurenKeyProbeHandler = handler;
                window.addEventListener('keydown', handler, true);
                window.__aurenKeyProbeCleanup = () => {
                    window.removeEventListener('keydown', handler, true);
                };
            }"""
        )
        p.keyboard.press(tecla)
        try:
            p.wait_for_function(
                "() => Boolean(window.__aurenKeyProbe && window.__aurenKeyProbe.count > 0)",
                timeout=1000,
            )
        except Exception:
            pass
        probe = p.evaluate("() => window.__aurenKeyProbe || {count: 0, key: ''}") or {}
        p.evaluate(
            """() => {
                if (typeof window.__aurenKeyProbeCleanup === 'function') {
                    window.__aurenKeyProbeCleanup();
                }
                window.__aurenKeyProbeCleanup = null;
                window.__aurenKeyProbeHandler = null;
            }"""
        )
        depois = _snapshot_pagina(p)
        abas_depois = _browser._abas_snapshot()
        evento_observado = bool(isinstance(probe, dict) and int(probe.get("count") or 0) > 0)

        return ToolResult.success(
            f"Pressionei a tecla '{tecla}'.",
            data={
                "tecla": {
                    "tecla": tecla,
                    "evento_observado": evento_observado,
                    "chave_observada": str(probe.get("key") or "") if isinstance(probe, dict) else "",
                    "estado_antes": antes,
                    "estado_depois": depois,
                    "abas_antes": abas_antes,
                    "abas_depois": abas_depois,
                }
            },
            tool_name="pressionar_tecla",
            conteudo_nao_confiavel=True,
        )

    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui pressionar '{tecla}': {erro}",
            error_code="key_failed",
            tool_name="pressionar_tecla",
        )


def _executar_navegacao(nome, metodo):
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        antes = _snapshot_pagina(p)
        metodo(p)
        depois = _snapshot_pagina(p)
        dados = {
            "url_antes": str(antes.get("url") or ""),
            "url_depois": str(depois.get("url") or ""),
            "titulo_antes": str(antes.get("titulo") or ""),
            "titulo_depois": str(depois.get("titulo") or ""),
            "estado_antes": antes,
            "estado_depois": depois,
            "mudou_url": antes.get("url") != depois.get("url"),
        }
        return ToolResult.success(
            nome,
            data={"navegacao": dados},
            tool_name=metodo.__name__ if hasattr(metodo, "__name__") else "browser_navigation",
        )
    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui {nome.lower()}: {erro}",
            error_code="browser_navigation_failed",
            tool_name="browser_navigation",
        )


def voltar_pagina():
    from tools import browser as _browser
    try:
        p = _browser.obter_pagina()
        antes = _snapshot_pagina(p)
        _instalar_probe_historico(p)
        p.go_back(wait_until="domcontentloaded", timeout=12000)
        evento_historico_observado = _ler_probe_historico(p)
        depois = _snapshot_pagina(p)
        return ToolResult.success(
            "Voltei para a pagina anterior.",
            data={"navegacao": {
                "operacao": "voltar",
                "url_antes": str(antes.get("url") or ""),
                "url_depois": str(depois.get("url") or ""),
                "mudou_url": antes.get("url") != depois.get("url"),
                "evento_historico_observado": evento_historico_observado,
                "titulo_antes": str(antes.get("titulo") or ""),
                "titulo_depois": str(depois.get("titulo") or ""),
            }},
            tool_name="voltar_pagina",
        )
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui voltar: {erro}", error_code="browser_back_failed", tool_name="voltar_pagina")


def avancar_pagina():
    from tools import browser as _browser
    try:
        p = _browser.obter_pagina()
        antes = _snapshot_pagina(p)
        _instalar_probe_historico(p)
        p.go_forward(wait_until="domcontentloaded", timeout=12000)
        evento_historico_observado = _ler_probe_historico(p)
        depois = _snapshot_pagina(p)
        return ToolResult.success(
            "Avancei para a proxima pagina.",
            data={"navegacao": {
                "operacao": "avancar",
                "url_antes": str(antes.get("url") or ""),
                "url_depois": str(depois.get("url") or ""),
                "mudou_url": antes.get("url") != depois.get("url"),
                "evento_historico_observado": evento_historico_observado,
                "titulo_antes": str(antes.get("titulo") or ""),
                "titulo_depois": str(depois.get("titulo") or ""),
            }},
            tool_name="avancar_pagina",
        )
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui avancar: {erro}", error_code="browser_forward_failed", tool_name="avancar_pagina")


def recarregar_pagina():
    from tools import browser as _browser
    try:
        p = _browser.obter_pagina()
        antes = _snapshot_pagina(p)
        p.reload(wait_until="domcontentloaded", timeout=12000)
        depois = _snapshot_pagina(p)
        return ToolResult.success(
            "Pagina recarregada.",
            data={"navegacao": {
                "operacao": "recarregar",
                "url": str(depois.get("url") or ""),
                "time_origin_antes": antes.get("time_origin"),
                "time_origin_depois": depois.get("time_origin"),
                "recarregamento_observado": (
                    antes.get("time_origin") is not None and
                    depois.get("time_origin") is not None and
                    antes.get("time_origin") != depois.get("time_origin")
                ),
            }},
            tool_name="recarregar_pagina",
        )
    except Exception as erro:
        return ToolResult.failure(f"Nao consegui recarregar: {erro}", error_code="browser_reload_failed", tool_name="recarregar_pagina")


def rolar_pagina(direcao, alvo=""):
    from tools import browser as _browser

    if direcao not in {"cima", "baixo", "inicio", "fim"}:
        return ToolResult.failure(
            "Direcao invalida. Use cima, baixo, inicio ou fim.",
            error_code="scroll_direction_invalid",
            tool_name="rolar_pagina",
        )

    try:
        p = _browser.obter_pagina()
        antes = float(p.evaluate("window.scrollY || 0") or 0)

        if direcao == "cima":
            p.mouse.wheel(0, -900)
            try:
                p.wait_for_function("window.scrollY < arguments[0]", antes, timeout=1500)
            except Exception:
                pass

        elif direcao == "baixo":
            p.mouse.wheel(0, 900)
            try:
                p.wait_for_function("window.scrollY > arguments[0]", antes, timeout=1500)
            except Exception:
                pass

        elif direcao == "inicio":
            p.evaluate("window.scrollTo({top: 0, behavior: 'auto'})")
            try:
                p.wait_for_function("window.scrollY === 0", timeout=1500)
            except Exception:
                pass

        elif direcao == "fim":
            p.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'auto'})")
            try:
                p.wait_for_function("window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2", timeout=1500)
            except Exception:
                pass

        depois = float(p.evaluate("window.scrollY || 0") or 0)
        altura_documento = float(p.evaluate(
            "Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0)"
        ) or 0)
        altura_viewport = float(p.evaluate("window.innerHeight || 0") or 0)
        alvo_normalizado = str(alvo or "").strip().casefold()
        alvo_encontrado = None
        if alvo_normalizado:
            try:
                alvo_encontrado = bool(p.evaluate(
                    """texto => (document.body?.innerText || '').toLocaleLowerCase().includes(texto)""",
                    alvo_normalizado,
                ))
            except Exception:
                alvo_encontrado = None

        return ToolResult.success(
            f"Pagina rolada para '{direcao}'.",
            data={
                "direcao": str(direcao),
                "scroll_y_antes": antes,
                "scroll_y_depois": depois,
                "scroll_height": altura_documento,
                "viewport_height": altura_viewport,
                "alvo": str(alvo or ""),
                "alvo_encontrado": alvo_encontrado,
            },
            tool_name="rolar_pagina",
        )

    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui rolar a pagina: {erro}",
            error_code="scroll_failed",
            tool_name="rolar_pagina",
        )