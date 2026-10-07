from __future__ import annotations

import re
from pathlib import Path

from config import BROWSER_PROFILE_DIR
from core.tool_result import ToolResult

playwright = None
browser = None
browser_context = None
pagina = None
modo_navegador = "visivel"


def _paginas_abertas():
    global browser_context

    if browser_context is None:
        return []

    try:
        return [
            p
            for p in browser_context.pages
            if not p.is_closed()
        ]
    except Exception:
        return []

def _esperar_documento_pronto(p, timeout_ms=5000):
    """Espera o estado final do documento sem confundir DOMContentLoaded com carga concluida."""
    try:
        estado = str(p.evaluate("() => document.readyState") or "")
    except Exception:
        return None

    if estado == "complete":
        return estado

    try:
        p.wait_for_function(
            "() => document.readyState === 'complete'",
            timeout=timeout_ms,
        )
    except Exception:
        pass

    try:
        return str(p.evaluate("() => document.readyState") or "") or None
    except Exception:
        return None


def _esperar_titulo(p, timeout_ms=1500):
    """Espera brevemente o titulo apos uma navegacao sem impor uma espera fixa longa."""
    try:
        titulo = (p.title() or "").strip()
    except Exception:
        titulo = ""

    if titulo or timeout_ms <= 0:
        return titulo

    try:
        p.wait_for_function(
            """() => {
                const t = document.title || '';
                return t.trim().length > 0;
            }""",
            timeout=timeout_ms,
        )
        return (p.title() or "").strip()
    except Exception:
        try:
            return (p.title() or "").strip()
        except Exception:
            return ""


def _descricao_aba(p, indice=None):
    titulo = _esperar_titulo(p)

    numero = f"Aba {indice}" if indice is not None else "Aba"
    url = p.url or "about:blank"
    if len(url) > 180:
        url = url[:177] + "..."

    return f"{numero}: {titulo or '[sem titulo]'} | {url}"

def _pagina_com_foco_real():
    """Retorna a unica pagina que o DOM identifica como focada.

    Com varias abas, se o navegador nao nos der uma resposta inequivoca,
    devolvemos None em vez de fingir que a referencia interna e a aba visual.
    """
    abas = _paginas_abertas()
    if len(abas) == 1:
        return abas[0]
    if len(abas) < 2:
        return None

    focadas = []
    for aba in abas:
        try:
            if bool(aba.evaluate("() => document.hasFocus()")):
                focadas.append(aba)
        except Exception:
            continue

    return focadas[0] if len(focadas) == 1 else None
def _estado_abas():
    abas = _paginas_abertas()
    if not abas:
        return "Nenhuma aba aberta."

    pagina_focada = _pagina_com_foco_real()
    linhas = [
        f"Abas abertas: {len(abas)}",
        f"Aba ativa: {abas.index(pagina_focada) + 1 if pagina_focada in abas else '?'}",
    ]

    for indice, aba in enumerate(abas, start=1):
        marcador = " [ATIVA]" if aba is pagina_focada else ""
        linhas.append(_descricao_aba(aba, indice) + marcador)

    return "\n".join(linhas)
def _abrir_contexto(modo):
    global playwright, browser, browser_context, pagina, modo_navegador

    if modo in {"visivel", "oculto"}:
        modo_navegador = modo

    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    playwright = sync_playwright().start()
    browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE_DIR),
        headless=(modo_navegador == "oculto"),
    )

    browser = browser_context.browser

    abas = _paginas_abertas()
    if abas:
        pagina = abas[-1]
    else:
        pagina = browser_context.new_page()

    return pagina

def reiniciar_navegador(modo=None):
    """Descarta a instancia atual e cria outra usando perfil persistente."""
    global playwright, browser, browser_context, pagina, modo_navegador

    if modo in {"visivel", "oculto"}:
        modo_navegador = modo

    try:
        if browser_context is not None:
            browser_context.close()
    except Exception:
        pass

    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass

    try:
        if playwright is not None:
            playwright.stop()
    except Exception:
        pass

    pagina = None
    browser_context = None
    browser = None
    playwright = None

    return _abrir_contexto(modo_navegador)

def obter_pagina():
    global playwright, browser, browser_context, pagina, modo_navegador

    if playwright is None or browser_context is None:
        return _abrir_contexto(modo_navegador)

    # Recriar a sessao so e justificavel quando o contexto informou
    # explicitamente que foi encerrado. Excecoes de leitura/operacao
    # nao devem destruir abas, formularios ou estado persistente.
    try:
        if hasattr(browser_context, "is_closed") and browser_context.is_closed():
            return reiniciar_navegador(modo_navegador)
    except Exception as erro:
        raise RuntimeError(f"Nao consegui determinar o estado do contexto do navegador: {erro}") from erro

    try:
        abas = [
            p
            for p in browser_context.pages
            if not p.is_closed()
        ]
    except Exception as erro:
        raise RuntimeError(f"Nao consegui consultar as abas abertas: {erro}") from erro

    if not abas:
        try:
            pagina = browser_context.new_page()
        except Exception as erro:
            raise RuntimeError(f"Nao consegui criar uma nova aba no contexto existente: {erro}") from erro
        return pagina

    if pagina is not None:
        try:
            if not pagina.is_closed() and pagina in abas:
                return pagina
        except Exception:
            # Nao destrua a sessao por uma falha de consulta da referencia
            # interna; abaixo escolhemos uma aba que sabemos estar aberta.
            pass

    pagina = abas[-1]
    return pagina

def _abas_snapshot() -> list[dict[str, object]]:
    abas = _paginas_abertas()
    pagina_focada = _pagina_com_foco_real()
    try:
        ativa = abas.index(pagina_focada) + 1
    except ValueError:
        ativa = None

    snapshot: list[dict[str, object]] = []
    for indice, aba in enumerate(abas, start=1):
        try:
            url = str(aba.url or "about:blank")
        except Exception:
            url = ""
        try:
            titulo = str(aba.title() or "[sem titulo]")
        except Exception:
            titulo = "[sem titulo]"
        snapshot.append({
            "indice": indice,
            "titulo": titulo,
            "url": url,
            "ativa": indice == ativa,
        })
    return snapshot


def listar_abas():
    """Lista as abas abertas e identifica a aba ativa."""
    abas = _paginas_abertas()
    snapshot = _abas_snapshot()
    return ToolResult.success(
        _estado_abas() if abas else "Nenhuma aba aberta no navegador.",
        data={"abas": snapshot},
        tool_name="listar_abas",
    )

def abrir_nova_aba(url="", modo="visivel"):
    """Abre uma nova aba e recupera a sessao se o contexto tiver sido encerrado."""
    global pagina, modo_navegador

    modo = str(modo or "visivel").strip().lower()
    if modo not in {"visivel", "oculto"}:
        modo = modo_navegador

    if browser_context is None or modo != modo_navegador:
        reiniciar_navegador(modo)

    quantidade_antes = len(_paginas_abertas())
    snapshot_antes = _abas_snapshot()

    def _navegar_e_responder(aba):
        global pagina
        pagina = aba

        if url:
            destino = str(url).strip()
            if not re.match(r"^https?://", destino, re.IGNORECASE):
                destino = "https://" + destino
            pagina.goto(destino, wait_until="domcontentloaded", timeout=30000)
            _esperar_titulo(pagina)

        try:
            pagina.bring_to_front()
        except Exception:
            pass

        abas_atuais = _paginas_abertas()
        numero = abas_atuais.index(pagina) + 1 if pagina in abas_atuais else 1
        snapshot = _abas_snapshot()
        return ToolResult.success(
            f"Nova aba aberta: {numero}\n"
            f"Titulo: {pagina.title() or '[sem titulo]'}\n"
            f"URL atual: {pagina.url or 'about:blank'}\n"
            f"{_estado_abas()}",
            data={
                "abas": {
                    "quantidade_antes": quantidade_antes,
                    "quantidade_depois": len(snapshot),
                    "antes": snapshot_antes,
                    "depois": snapshot,
                    "aba_ativa_depois": numero,
                    "url_ativa_depois": str(pagina.url or "about:blank"),
                },
            },
            tool_name="abrir_nova_aba",
        )

    try:
        return _navegar_e_responder(browser_context.new_page())
    except Exception as erro:
        # Depois de fechar a ultima aba, alguns ambientes podem deixar o
        # BrowserContext sem uma referencia utilizavel. Recria o contexto
        # persistente (mantendo cookies/local storage) e usa a pagina inicial
        # recem-criada como a nova aba solicitada.
        try:
            reiniciar_navegador(modo)
            if pagina is None or pagina.is_closed():
                pagina = obter_pagina()
            return _navegar_e_responder(pagina)
        except Exception as segundo_erro:
            return ToolResult.failure(
                f"Nao consegui abrir nova aba: {segundo_erro}. Erro original: {erro}",
                error_code="open_tab_failed",
                tool_name="abrir_nova_aba",
            )

def trocar_aba(indice):
    """Torna ativa a aba indicada pela ordem atual, começando em 1."""
    global pagina

    abas = _paginas_abertas()
    quantidade_antes = len(abas)
    snapshot_antes = _abas_snapshot()
    try:
        indice = int(indice)
    except (TypeError, ValueError):
        return ToolResult.failure(
            "Indice de aba invalido.",
            error_code="invalid_tab_index",
            tool_name="trocar_aba",
        )

    if indice < 1 or indice > len(abas):
        return ToolResult.failure(
            f"Nao existe a aba {indice}. Existem {len(abas)} abas abertas.",
            error_code="tab_not_found",
            tool_name="trocar_aba",
        )

    pagina = abas[indice - 1]
    try:
        pagina.bring_to_front()
    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui tornar a aba {indice} visualmente ativa: {erro}",
            error_code="tab_focus_failed",
            tool_name="trocar_aba",
            data={
                "abas": {
                    "quantidade_antes": quantidade_antes,
                    "quantidade_depois": quantidade_antes,
                    "aba_ativa_desejada": indice,
                    "antes": snapshot_antes,
                }
            },
        )
    snapshot = _abas_snapshot()
    return ToolResult.success(
        f"Troquei para a aba {indice}.\n"
        f"Titulo: {pagina.title() or '[sem titulo]'}\n"
        f"URL atual: {pagina.url or 'about:blank'}\n"
        f"{_estado_abas()}",
        data={
            "abas": {
                "quantidade_antes": quantidade_antes,
                "quantidade_depois": len(snapshot),
                "aba_ativa_antes": next(
                    (item["indice"] for item in snapshot_antes if item.get("ativa")),
                    None,
                ),
                "aba_ativa_depois": indice,
                "url_ativa_depois": str(pagina.url or "about:blank"),
                "depois": snapshot,
            },
        },
        tool_name="trocar_aba",
    )

def fechar_aba(indice=None):
    """Fecha a aba indicada; por padrão, fecha a aba ativa."""
    global pagina

    abas = _paginas_abertas()
    if not abas:
        return ToolResult.failure(
            "Nenhuma aba aberta no navegador.",
            error_code="no_open_tabs",
            data={"abas": []},
            tool_name="fechar_aba",
        )

    if indice is None:
        alvo = pagina if pagina in abas else abas[-1]
    else:
        try:
            indice = int(indice)
        except (TypeError, ValueError):
            return ToolResult.failure(
                "Indice de aba invalido.",
                error_code="invalid_tab_index",
                tool_name="fechar_aba",
            )
        if indice == 0:
            alvo = pagina if pagina in abas else abas[-1]
        else:
            if indice < 1 or indice > len(abas):
                return ToolResult.failure(
                    f"Nao existe a aba {indice}. Existem {len(abas)} abas abertas.",
                    error_code="tab_not_found",
                    tool_name="fechar_aba",
                )
            alvo = abas[indice - 1]

    posicao = abas.index(alvo)
    indice_fechado = posicao + 1
    quantidade_antes = len(abas)
    snapshot_antes = _abas_snapshot()
    alvo.close()

    restantes = _paginas_abertas()
    if restantes:
        novo_indice = min(posicao, len(restantes) - 1)
        pagina = restantes[novo_indice]
        try:
            pagina.bring_to_front()
        except Exception as erro:
            return ToolResult.failure(
                f"Aba fechada, mas nao consegui tornar a aba {novo_indice + 1} visualmente ativa: {erro}",
                error_code="tab_focus_failed",
                tool_name="fechar_aba",
                data={
                    "abas": {
                        "quantidade_antes": quantidade_antes,
                        "quantidade_depois": len(restantes),
                        "aba_fechada": indice_fechado,
                    }
                },
            )
        snapshot = _abas_snapshot()
        return ToolResult.success(
            f"Fechei a aba {indice_fechado}.\n"
            f"{_estado_abas()}",
            data={
                "abas": {
                    "quantidade_antes": quantidade_antes,
                    "quantidade_depois": len(snapshot),
                    "aba_fechada": indice_fechado,
                    "aba_ativa_antes": next(
                        (item["indice"] for item in snapshot_antes if item.get("ativa")),
                        None,
                    ),
                    "aba_ativa_depois": novo_indice + 1,
                    "url_ativa_depois": str(pagina.url or "about:blank"),
                    "antes": snapshot_antes,
                    "depois": snapshot,
                },
            },
            tool_name="fechar_aba",
        )

    pagina = None
    return ToolResult.success(
        "Fechei a ultima aba. O navegador continua aberto sem abas.",
        data={
            "abas": {
                "quantidade_antes": quantidade_antes,
                "quantidade_depois": 0,
                "aba_fechada": indice_fechado,
                "aba_ativa_antes": next(
                    (item["indice"] for item in snapshot_antes if item.get("ativa")),
                    None,
                ),
                "aba_ativa_depois": None,
                "url_ativa_depois": None,
                "antes": snapshot_antes,
                "depois": [],
            },
        },
        tool_name="fechar_aba",
    )

def fechar_navegador():
    global playwright, browser, browser_context, pagina

    try:
        if browser_context is not None:
            browser_context.close()
    except Exception:
        pass

    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass

    try:
        if playwright is not None:
            playwright.stop()
    except Exception:
        pass

    pagina = None
    browser_context = None
    browser = None
    playwright = None

def navegar_navegador(url, modo="visivel"):
    url = str(url or "").strip()
    modo = str(modo or "visivel").strip().lower()
    if modo not in {"visivel", "oculto"}:
        return ToolResult.failure(
            "Modo de navegador invalido. Use 'visivel' ou 'oculto'.",
            error_code="browser_mode_invalid",
            tool_name="navegar_navegador",
        )

    global modo_navegador, browser_context
    if not url:
        return ToolResult.failure(
            "URL vazia.",
            error_code="browser_url_empty",
            tool_name="navegar_navegador",
        )

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    if modo != modo_navegador or browser_context is None:
        try:
            p = reiniciar_navegador(modo)
        except Exception as erro:
            return ToolResult.failure(
                f"Nao consegui preparar o navegador: {erro}",
                error_code="browser_init_failed",
                tool_name="navegar_navegador",
            )
    else:
        p = None

    tentativa_restart = False
    try:
        if p is None:
            p = obter_pagina()
        antes_url = str(getattr(p, "url", "") or "")
        antes_titulo = _esperar_titulo(p)
        p.goto(url, wait_until="domcontentloaded", timeout=30000)
        ready_state = _esperar_documento_pronto(p)
        depois_url = str(getattr(p, "url", "") or url)
        depois_titulo = _esperar_titulo(p)
        return ToolResult.success(
            f"Naveguei para: {depois_titulo or '[sem titulo]'}\nURL atual: {depois_url}\nModo do navegador: {modo}",
            data={
                "navegacao": {
                    "operacao": "navegar",
                    "url_solicitada": url,
                    "url_antes": antes_url,
                    "url_depois": depois_url,
                    "titulo_antes": antes_titulo,
                    "titulo_depois": depois_titulo,
                    "ready_state_depois": ready_state,
                    "mudou_url": antes_url != depois_url,
                    "modo": modo,
                }
            },
            tool_name="navegar_navegador",
            conteudo_nao_confiavel=False,
        )
    except Exception as erro:
        pagina_fechada = False
        contexto_fechado = False
        try:
            pagina_fechada = bool(p.is_closed()) if p is not None else False
        except Exception:
            pass
        try:
            contexto_fechado = bool(browser_context is not None and browser_context.is_closed())
        except Exception:
            pass

        if pagina_fechada or contexto_fechado:
            try:
                p = reiniciar_navegador(modo)
                tentativa_restart = True
                try:
                    p.goto(url, wait_until="domcontentloaded", timeout=30000)
                    depois_url = str(getattr(p, "url", "") or url)
                    depois_titulo = _esperar_titulo(p)
                    return ToolResult.success(
                        f"Naveguei para: {depois_titulo or '[sem titulo]'}\nURL atual: {depois_url}\nModo do navegador: {modo}",
                        data={
                            "navegacao": {
                                "operacao": "navegar",
                                "url_solicitada": url,
                                "url_antes": antes_url if 'antes_url' in locals() else None,
                                "url_depois": depois_url,
                                "mudou_url": True,
                                "modo": modo,
                                "sessao_recriada": True,
                            }
                        },
                        tool_name="navegar_navegador",
                    )
                except Exception as erro_retry:
                    erro = erro_retry
            except Exception as erro_restart:
                erro = erro_restart

        return ToolResult.failure(
            f"Nao consegui navegar para '{url}': {erro}",
            error_code="browser_navigation_failed" if not tentativa_restart else "browser_navigation_retry_failed",
            tool_name="navegar_navegador",
        )

from tools.browser_reading import ler_pagina

from tools.browser_elements import (
    encontrar_elemento,
    clicar_elemento,
    preencher_elemento,
)


from tools.browser_navigation import (
    pressionar_tecla,
    voltar_pagina,
    avancar_pagina,
    recarregar_pagina,
    rolar_pagina,
)
