from __future__ import annotations

import json
import re

from core.tool_result import ToolResult
from core.utils import normalizar_nome


def encontrar_elemento(alvo, indice=1, preferir_campo=False):
    from tools import browser as _browser

    p = _browser.obter_pagina()
    alvo = (alvo or "").strip()

    if not alvo:
        raise ValueError("O alvo nao pode estar vazio.")

    indice = max(1, indice)
    padrao = re.compile(
        re.escape(alvo),
        re.IGNORECASE
    )
    padrao_exato = re.compile(
        r"^\s*" + re.escape(alvo) + r"\s*$",
        re.IGNORECASE
    )

    # Para preencher, campos de entrada tem prioridade absoluta sobre
    # botoes e links. Isso evita confundir "pesquisar" com "Pesquisa por voz".
    if preferir_campo:
        papeis = [
            "searchbox",
            "textbox",
            "combobox",
            "button",
            "link",
            "tab",
            "menuitem",
            "checkbox",
            "radio"
        ]
    else:
        papeis = [
            "button",
            "link",
            "textbox",
            "searchbox",
            "tab",
            "menuitem",
            "checkbox",
            "radio",
            "combobox"
        ]

    def visiveis(encontrados):
        saida = []
        for i in range(encontrados.count()):
            elemento = encontrados.nth(i)
            try:
                if elemento.is_visible():
                    saida.append(elemento)
            except Exception:
                pass
        return saida

    def procurar_atributo(atributo, tags=None):
        valor = json.dumps(alvo, ensure_ascii=False)
        if tags:
            seletor = ", ".join(
                f"{tag}[{atributo}={valor}]"
                for tag in tags
            )
        else:
            seletor = f"[{atributo}={valor}]"

        try:
            encontrados = visiveis(p.locator(seletor))
            if len(encontrados) >= indice:
                return encontrados[indice - 1]
        except Exception:
            pass

        return None

    # Identificadores HTML exatos ajudam quando a interface não expõe um
    # nome acessível estável, como um input com name=search_query.
    if preferir_campo:
        atributos = [
            ("id", None),
            ("name", ["input", "textarea", "select"]),
            ("aria-label", None),
            ("placeholder", ["input", "textarea"]),
        ]

        for atributo, tags in atributos:
            encontrado = procurar_atributo(atributo, tags)
            if encontrado is not None:
                return encontrado

    # Primeiro tenta correspondencia exata do nome acessivel.
    for papel in papeis:
        try:
            encontrados = visiveis(
                p.get_by_role(papel, name=padrao_exato)
            )
            if len(encontrados) >= indice:
                return encontrados[indice - 1]
        except Exception:
            pass

    # Depois usa correspondencia parcial como fallback.
    for papel in papeis:
        try:
            encontrados = visiveis(
                p.get_by_role(papel, name=padrao)
            )
            if len(encontrados) >= indice:
                return encontrados[indice - 1]
        except Exception:
            pass

    # Por ultimo, tenta label, placeholder e texto. Para preenchimento,
    # label/placeholder tambem ficam antes de texto generico.
    metodos = [
        p.get_by_label,
        p.get_by_placeholder,
        p.get_by_text
    ]

    for metodo in metodos:
        for padrao_atual in (padrao_exato, padrao):
            try:
                encontrados = visiveis(metodo(padrao_atual))
                if len(encontrados) >= indice:
                    return encontrados[indice - 1]
            except Exception:
                pass

    raise ValueError(
        f"Nao encontrei o elemento '{alvo}' na pagina."
    )

def clicar_elemento(alvo, indice=1):
    from tools import browser as _browser

    try:
        p = _browser.obter_pagina()
        url_anterior = p.url
        elemento = encontrar_elemento(
            alvo,
            indice
        )

        # Identifica informacao do elemento antes do clique para melhorar
        # a verificacao local de conclusao sem chamar o modelo novamente.
        try:
            tag_elemento = elemento.evaluate("el => el.tagName.toLowerCase()")
            href_elemento = elemento.get_attribute("href") or ""
        except Exception:
            tag_elemento = ""
            href_elemento = ""

        # Nao esperamos o carregamento completo da pagina aqui.
        # O navegador continua carregando sozinho e o proximo passo pode
        # consultar a pagina quando realmente precisar.
        abas_antes = list(_browser._paginas_abertas())
        elemento.click(timeout=10000)

        # Alguns sites abrem links em nova aba/janela. Quando isso acontece,
        # a nova pagina passa a ser a aba ativa do Auren.
        try:
            p.wait_for_timeout(250)
        except Exception:
            pass

        abas_depois = list(_browser._paginas_abertas())
        novas_abas = [aba for aba in abas_depois if aba not in abas_antes]
        if novas_abas:
            _browser.pagina = novas_abas[-1]
            p = novas_abas[-1]
        else:
            p = _browser.obter_pagina()

        url_atual = p.url
        navegacao = "sim" if novas_abas or url_atual != url_anterior else "nao"

        return ToolResult.success(
            f"Cliquei em '{alvo}'.\n"
            f"Elemento: tag={tag_elemento} | href={href_elemento}\n"
            f"URL anterior: {url_anterior}\n"
            f"URL atual: {url_atual}\n"
            f"Navegacao: {navegacao}",
            data={
                "clique": {
                    "alvo": str(alvo),
                    "indice": int(indice),
                    "tag": str(tag_elemento),
                    "href": str(href_elemento),
                    "url_anterior": str(url_anterior),
                    "url_atual": str(url_atual),
                    "navegacao": navegacao == "sim",
                    "nova_aba": bool(novas_abas),
                },
            },
            tool_name="clicar_elemento",
        )

    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui clicar em '{alvo}': {erro}",
            error_code="click_failed",
            tool_name="clicar_elemento",
        )

def preencher_elemento(alvo, texto, indice=1):
    try:
        elemento = encontrar_elemento(
            alvo,
            indice,
            preferir_campo=True
        )

        elemento.fill(
            texto,
            timeout=10000
        )

        return (
            f"Preenchi '{alvo}' com o texto informado."
        )

    except Exception as erro:
        return (
            f"Nao consegui preencher '{alvo}': {erro}"
        )

