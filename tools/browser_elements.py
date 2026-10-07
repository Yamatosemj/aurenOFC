from __future__ import annotations

import json
import re

from core.browser_verification import _compromisso_preenchimento_sensivel
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

def obter_evidencia_risco_clique(alvo, indice=1):
    """Inspeciona somente a estrutura do elemento para a decisao de permissao."""
    try:
        elemento = encontrar_elemento(alvo, indice)
        evidencia = elemento.evaluate(
            """el => {
                const form = el.closest('form');
                const attr = nome => el.getAttribute(nome) || '';
                return {
                    tag: String(el.tagName || '').toLowerCase(),
                    role: attr('role').toLowerCase(),
                    type: attr('type').toLowerCase(),
                    href: attr('href'),
                    target: attr('target').toLowerCase(),
                    download: el.hasAttribute('download'),
                    onclick: attr('onclick'),
                    disabled: Boolean(el.disabled),
                    contenteditable: attr('contenteditable').toLowerCase(),
                    form: form ? {
                        method: String(form.getAttribute('method') || 'get').toLowerCase(),
                        action: String(form.getAttribute('action') || ''),
                    } : null,
                };
            }"""
        )
        if not isinstance(evidencia, dict):
            return {"ok": False, "evidencia": {}}
        return {"ok": True, "evidencia": evidencia}
    except Exception as erro:
        return {"ok": False, "evidencia": {}, "erro": str(erro)}

def clicar_elemento(alvo, indice=1):
    from tools import browser as _browser

    def _capturar_estado_controle(elemento):
        try:
            estado = elemento.evaluate(
                """
                el => {
                    const attr = nome => {
                        const valor = el.getAttribute(nome);
                        return valor === null ? null : valor;
                    };

                    const id = attr('id') || '';
                    const name = attr('name') || '';
                    const ariaLabel = attr('aria-label') || '';
                    const placeholder = attr('placeholder') || '';
                    const role = attr('role') || '';
                    const texto = String(
                        el.innerText || el.textContent || ''
                    ).replace(/\s+/g, ' ').trim().slice(0, 120);

                    const fingerprintTexto = (() => {
                        const alvo = el.parentElement || el;
                        const bruto = String(alvo.outerHTML || '').replace(/\s+/g, ' ').slice(0, 12000);
                        let hash = 1469598103934665603n;
                        for (let i = 0; i < bruto.length; i += 1) {
                            hash ^= BigInt(bruto.charCodeAt(i));
                            hash = BigInt.asUintN(64, hash * 1099511628211n);
                        }
                        return hash.toString(16).padStart(16, '0');
                    })();

                    let chave = '';
                    if (id) chave = 'id:' + id;
                    else if (name) chave = 'name:' + name;
                    else if (ariaLabel) chave = 'aria:' + ariaLabel;
                    else if (placeholder) chave = 'placeholder:' + placeholder;
                    else if (texto) chave = 'texto:' + texto;

                    return {
                        chave,
                        id: id.slice(0, 120),
                        name: name.slice(0, 120),
                        ariaLabel: ariaLabel.slice(0, 180),
                        placeholder: placeholder.slice(0, 120),
                        role: role.slice(0, 80),
                        tag: String(el.tagName || '').toLowerCase(),
                        domFingerprint: fingerprintTexto,
                        estados: {
                            'aria-expanded': attr('aria-expanded'),
                            'aria-pressed': attr('aria-pressed'),
                            'aria-selected': attr('aria-selected'),
                            'aria-checked': attr('aria-checked'),
                            'checked': ('checked' in el) ? Boolean(el.checked) : null,
                            'selected': ('selected' in el) ? Boolean(el.selected) : null,
                            'open': ('open' in el)
                                ? Boolean(el.open)
                                : (el.tagName === 'SUMMARY' && el.closest('details')
                                    ? Boolean(el.closest('details').open)
                                    : null),
                            'details-open': (el.tagName === 'SUMMARY' && el.closest('details'))
                                ? Boolean(el.closest('details').open)
                                : (el.tagName === 'DETAILS' ? Boolean(el.open) : null),
                            'data-state': attr('data-state')
                        }
                    };
                }
                """
            )
            if isinstance(estado, dict):
                return estado
        except Exception:
            pass
        return {
            "chave": "",
            "id": "",
            "name": "",
            "ariaLabel": "",
            "placeholder": "",
            "role": "",
            "tag": "",
            "estados": {},
        }

    def _capturar_estado_pagina(pagina):
        try:
            estado = pagina.evaluate(
                """
                () => {
                    const visivel = el => {
                        const rect = el.getBoundingClientRect();
                        const cs = getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 &&
                               cs.visibility !== 'hidden' &&
                               cs.display !== 'none' &&
                               cs.opacity !== '0' &&
                               cs.pointerEvents !== 'none';
                    };

                    const contar = seletores => Array.from(
                        document.querySelectorAll(seletores)
                    ).filter(visivel).length;

                    return {
                        dialogos: contar('dialog, [role="dialog"], [role="alertdialog"]'),
                        menus: contar('[role="menu"]'),
                        listboxes: contar('[role="listbox"]'),
                        popovers: (() => {
                            try {
                                return Array.from(document.querySelectorAll('[popover]'))
                                    .filter(el => el.matches(':popover-open') && visivel(el)).length;
                            } catch (_) {
                                return 0;
                            }
                        })(),
                        details_abertos: contar('details[open]')
                    };
                }
                """
            )
            if isinstance(estado, dict):
                return {
                    "dialogos": int(estado.get("dialogos", 0)),
                    "menus": int(estado.get("menus", 0)),
                    "listboxes": int(estado.get("listboxes", 0)),
                    "popovers": int(estado.get("popovers", 0)),
                    "details_abertos": int(estado.get("details_abertos", 0)),
                }
        except Exception:
            pass
        return {}

    def _sinal_controle(antes, depois):
        estados_antes = antes.get("estados", {})
        estados_depois = depois.get("estados", {})
        for atributo in (
            "aria-expanded",
            "aria-pressed",
            "aria-selected",
            "aria-checked",
            "checked",
            "selected",
            "open",
            "details-open",
            "data-state",
        ):
            valor_antes = estados_antes.get(atributo)
            valor_depois = estados_depois.get(atributo)
            if valor_antes is not None and valor_depois is not None:
                if valor_antes != valor_depois:
                    return {
                        "atributo": atributo,
                        "antes": valor_antes,
                        "depois": valor_depois,
                    }
        fingerprint_antes = str(antes.get("domFingerprint") or "")
        fingerprint_depois = str(depois.get("domFingerprint") or "")
        if fingerprint_antes and fingerprint_depois and fingerprint_antes != fingerprint_depois:
            return {
                "atributo": "domFingerprint",
                "antes": fingerprint_antes,
                "depois": fingerprint_depois,
            }
        return None

    try:
        p = _browser.obter_pagina()
        url_anterior = p.url
        elemento = encontrar_elemento(
            alvo,
            indice
        )

        estado_controle_antes = _capturar_estado_controle(elemento)
        estado_pagina_antes = _capturar_estado_pagina(p)

        try:
            href_elemento = elemento.get_attribute("href") or ""
        except Exception:
            href_elemento = ""

        tag_elemento = str(estado_controle_antes.get("tag") or "")

        abas_antes = list(_browser._paginas_abertas())
        popup = None
        click_executado = False
        popup_timeout = 1200
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except Exception:
            PlaywrightTimeoutError = TimeoutError

        # Instala um observador antes do clique para aguardar mudancas reais
        # em vez de dormir uma quantidade arbitraria de milissegundos.
        try:
            p.evaluate(
                """() => {
                    if (window.__aurenClickObserver) {
                        window.__aurenClickObserver.disconnect();
                    }
                    const estado = {mutated: false};
                    const observer = new MutationObserver(() => {
                        estado.mutated = true;
                    });
                    observer.observe(document.documentElement || document, {
                        subtree: true,
                        childList: true,
                        attributes: true,
                        characterData: true,
                    });
                    window.__aurenClickProbe = estado;
                    window.__aurenClickObserver = observer;
                }"""
            )
        except Exception:
            pass

        try:
            with p.expect_popup(timeout=popup_timeout) as popup_info:
                elemento.click(timeout=10000)
                click_executado = True
            popup = popup_info.value
        except PlaywrightTimeoutError:
            if not click_executado:
                # O timeout pode ter vindo do proprio click, nao da ausencia de popup.
                try:
                    elemento.click(timeout=10000)
                    click_executado = True
                except Exception as erro:
                    raise erro
        except AttributeError:
            elemento.click(timeout=10000)
            click_executado = True
        except Exception as erro:
            if not click_executado:
                raise erro

        if popup is not None:
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass

        try:
            p.wait_for_function(
                """() => Boolean(window.__aurenClickProbe?.mutated)""",
                timeout=2000,
            )
        except Exception:
            pass
        try:
            p.evaluate(
                """() => {
                    if (window.__aurenClickObserver) {
                        window.__aurenClickObserver.disconnect();
                    }
                    window.__aurenClickObserver = null;
                }"""
            )
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
        estado_controle_depois = _capturar_estado_controle(elemento)
        estado_pagina_depois = _capturar_estado_pagina(p)

        navegacao = "sim" if novas_abas or url_atual != url_anterior else "nao"

        efeito = {
            "controle": {
                "chave": estado_controle_antes.get("chave", ""),
                "id": estado_controle_antes.get("id", ""),
                "name": estado_controle_antes.get("name", ""),
                "aria_label": estado_controle_antes.get("ariaLabel", ""),
                "placeholder": estado_controle_antes.get("placeholder", ""),
                "role": estado_controle_antes.get("role", ""),
                "tag": tag_elemento,
                "dom_fingerprint": estado_controle_antes.get("domFingerprint", ""),
            },
            "pagina_antes": estado_pagina_antes,
            "pagina_depois": estado_pagina_depois,
        }

        sinal = _sinal_controle(
            estado_controle_antes,
            estado_controle_depois,
        )
        if sinal:
            efeito["sinal"] = {
                "tipo": "controle",
                **sinal,
            }
        else:
            for tipo in ("dialogos", "menus", "listboxes", "popovers", "details_abertos"):
                antes = estado_pagina_antes.get(tipo)
                depois = estado_pagina_depois.get(tipo)
                if isinstance(antes, int) and isinstance(depois, int) and antes != depois:
                    efeito["sinal"] = {
                        "tipo": "pagina",
                        "alvo": tipo,
                        "antes": antes,
                        "depois": depois,
                    }
                    break

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
                    "tag": tag_elemento,
                    "href": str(href_elemento),
                    "url_anterior": str(url_anterior),
                    "url_atual": str(url_atual),
                    "navegacao": navegacao == "sim",
                    "nova_aba": bool(novas_abas),
                    "efeito": efeito,
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
            preferir_campo=True,
        )

        atributos = {}
        for nome in ("type", "name", "id", "aria-label", "placeholder", "autocomplete"):
            try:
                atributos[nome] = str(elemento.get_attribute(nome) or "")
            except Exception:
                atributos[nome] = ""
        texto_identificacao = " ".join(atributos.values()).casefold()
        sensivel = (
            atributos.get("type", "").casefold() == "password"
            or bool(re.search(
                r"password|senha|token|secret|segredo|pin|cvv|cvc|2fa|one-time-code|verification|verificacao|codigo",
                texto_identificacao,
            ))
        )

        elemento.fill(texto, timeout=10000)

        observado = None
        leitura_disponivel = True
        try:
            observado = elemento.input_value(timeout=10000)
        except Exception:
            leitura_disponivel = False

        verificado_localmente = leitura_disponivel and observado == str(texto)
        if leitura_disponivel and not verificado_localmente:
            return ToolResult.failure(
                f"Preenchimento de '{alvo}' nao correspondeu ao valor solicitado.",
                error_code="fill_verification_failed",
                data={
                    "preenchimento": {
                        "alvo": str(alvo),
                        "indice": int(indice),
                        "sensivel": sensivel,
                        "verificado_localmente": False,
                    }
                },
                tool_name="preencher_elemento",
            )

        compromisso = None
        if sensivel and verificado_localmente:
            compromisso = _compromisso_preenchimento_sensivel(str(observado))

        return ToolResult.success(
            f"Preenchi '{alvo}' com o texto informado.",
            data={
                "preenchimento": {
                    "alvo": str(alvo),
                    "indice": int(indice),
                    "sensivel": sensivel,
                    "verificado_localmente": bool(verificado_localmente),
                    "compromisso": compromisso,
                }
            },
            tool_name="preencher_elemento",
        )

    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui preencher '{alvo}': {erro}",
            error_code="fill_failed",
            tool_name="preencher_elemento",
        )
