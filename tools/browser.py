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

def _estado_abas():
    abas = _paginas_abertas()
    if not abas:
        return "Nenhuma aba aberta."

    try:
        indice_atual = abas.index(pagina) + 1
    except ValueError:
        indice_atual = None

    linhas = [
        f"Abas abertas: {len(abas)}",
        f"Aba ativa: {indice_atual or '?'}",
    ]

    for indice, aba in enumerate(abas, start=1):
        marcador = " [ATIVA]" if aba is pagina else ""
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

    try:
        if playwright is None or browser_context is None:
            return _abrir_contexto(modo_navegador)

        abas = _paginas_abertas()
        if not abas:
            pagina = browser_context.new_page()
            return pagina

        if pagina is not None and not pagina.is_closed() and pagina in abas:
            return pagina

        pagina = abas[-1]
        return pagina
    except Exception:
        return reiniciar_navegador(modo_navegador)

def _abas_snapshot() -> list[dict[str, object]]:
    abas = _paginas_abertas()
    try:
        ativa = abas.index(pagina) + 1
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
    if not abas:
        return "Nenhuma aba aberta no navegador."
    return _estado_abas()

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
            return (
                "Nao consegui abrir nova aba: "
                f"{segundo_erro}. Erro original: {erro}"
            )

def trocar_aba(indice):
    """Torna ativa a aba indicada pela ordem atual, começando em 1."""
    global pagina

    abas = _paginas_abertas()
    quantidade_antes = len(abas)
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
                "aba_ativa_antes": None,
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
        return "Nenhuma aba aberta no navegador."

    if indice is None:
        alvo = pagina if pagina in abas else abas[-1]
    else:
        try:
            indice = int(indice)
        except (TypeError, ValueError):
            return "Indice de aba invalido."
        if indice == 0:
            alvo = pagina if pagina in abas else abas[-1]
        else:
            if indice < 1 or indice > len(abas):
                return f"Nao existe a aba {indice}. Existem {len(abas)} abas abertas."
            alvo = abas[indice - 1]

    posicao = abas.index(alvo)
    indice_fechado = posicao + 1
    quantidade_antes = len(abas)
    alvo.close()

    restantes = _paginas_abertas()
    if restantes:
        novo_indice = min(posicao, len(restantes) - 1)
        pagina = restantes[novo_indice]
        snapshot = _abas_snapshot()
        return ToolResult.success(
            f"Fechei a aba {indice_fechado}.\n"
            f"{_estado_abas()}",
            data={
                "abas": {
                    "quantidade_antes": quantidade_antes,
                    "quantidade_depois": len(snapshot),
                    "aba_fechada": indice_fechado,
                    "aba_ativa_depois": novo_indice + 1,
                    "url_ativa_depois": str(pagina.url or "about:blank"),
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
                "aba_ativa_depois": None,
                "url_ativa_depois": None,
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
    url = url.strip()
    modo = str(modo or "visivel").strip().lower()
    if modo not in {"visivel", "oculto"}:
        modo = "visivel"

    # O modo e decidido no primeiro passo da navegacao. Se o navegador atual
    # estiver em outro modo, recriamos a sessao antes de abrir a URL.
    global modo_navegador, browser_context
    if modo != modo_navegador or browser_context is None:
        try:
            p = reiniciar_navegador(modo)
        except Exception:
            p = None
    else:
        p = None

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    ultimo_erro = None

    for tentativa in range(2):
        try:
            if p is None:
                p = obter_pagina()
            p.goto(
                url,
                # DOMContentLoaded oferece um ponto seguro para ler o titulo
                # sem aguardar recursos pesados da pagina inteira.
                wait_until="domcontentloaded",
                timeout=30000
            )
            titulo = _esperar_titulo(p)
            return (
                f"Naveguei para: {titulo or '[sem titulo]'}\n"
                f"URL atual: {p.url}\n"
                f"Modo do navegador: {modo}"
            )
        except Exception as erro:
            ultimo_erro = erro
            if tentativa == 0:
                try:
                    # A primeira falha pode ser apenas uma referencia para uma
                    # pagina/browser que foi fechado manualmente. Recria e troca
                    # explicitamente a referencia usada na segunda tentativa.
                    p = reiniciar_navegador(modo)
                except Exception as reinicio_erro:
                    ultimo_erro = reinicio_erro
                    break

    return f"Nao consegui navegar para '{url}': {ultimo_erro}"

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
