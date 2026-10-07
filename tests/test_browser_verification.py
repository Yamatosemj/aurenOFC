from core.browser_verification import verificar_resultado_navegador


def _contexto(abas):
    return {"abas": abas, "pagina": "conteudo"}



def _dados_clique_navegacao(*, url_atual="https://youtube.com/watch?v=123", href="https://youtube.com/watch?v=123", url_anterior="https://google.com"):
    return {
        "clique": {
            "alvo": "resultado",
            "indice": 1,
            "tag": "a",
            "href": href,
            "url_anterior": url_anterior,
            "url_atual": url_atual,
            "navegacao": True,
            "nova_aba": False,
        }
    }


def test_click_verification_accepts_matching_navigation_href():
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"resultado","indice":1}',
        _contexto(
            "Abas abertas: 1\n"
            "Aba ativa: 1\n"
            "Aba 1: YouTube | https://youtube.com/watch?v=123 [ATIVA]"
        ),
        _dados_clique_navegacao(),
    ) is True


def test_click_verification_rejects_wrong_navigation_href():
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"resultado","indice":1}',
        _contexto(
            "Abas abertas: 1\n"
            "Aba ativa: 1\n"
            "Aba 1: GitHub | https://github.com [ATIVA]"
        ),
        _dados_clique_navegacao(
            url_atual="https://github.com",
        ),
    ) is False


def test_non_navigational_click_is_not_claimed_as_verified():
    dados = _dados_clique_navegacao()
    dados["clique"]["navegacao"] = False
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        _contexto(
            "Abas abertas: 1\n"
            "Aba ativa: 1\n"
            "Aba 1: Site | https://example.com [ATIVA]"
        ),
        dados,
    ) is None
def test_navigation_verification_accepts_equivalent_normalized_url():
    dados = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: YouTube | https://www.youtube.com/ [ATIVA]"
    )

    assert verificar_resultado_navegador(
        "navegar_navegador",
        '{"url":"youtube.com"}',
        dados,
    ) is True


def test_navigation_verification_rejects_wrong_active_url():
    dados = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: GitHub | https://github.com/ [ATIVA]"
    )

    assert verificar_resultado_navegador(
        "navegar_navegador",
        '{"url":"youtube.com"}',
        dados,
    ) is False


def test_tab_switch_verification_checks_active_tab_index():
    dados = _contexto(
        "Abas abertas: 3\n"
        "Aba ativa: 2\n"
        "Aba 1: Inicio | https://example.com [ATIVA]\n"
        "Aba 2: Editor | https://example.com/editor [ATIVA]\n"
        "Aba 3: Ajuda | https://example.com/help"
    )

    assert verificar_resultado_navegador(
        "trocar_aba",
        '{"indice":2}',
        dados,
    ) is True

    assert verificar_resultado_navegador(
        "trocar_aba",
        '{"indice":3}',
        dados,
    ) is False


def test_open_new_tab_without_target_uses_generic_verification():
    dados = _contexto(
        "Abas abertas: 2\n"
        "Aba ativa: 2\n"
        "Aba 1: Inicio | https://example.com\n"
        "Aba 2: Nova | about:blank [ATIVA]"
    )

    assert verificar_resultado_navegador(
        "abrir_nova_aba",
        '{"url":""}',
        dados,
    ) is None


def test_unsupported_browser_action_returns_generic_verification():
    dados = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]"
    )

    assert verificar_resultado_navegador(
        "rolar_pagina",
        '{"direcao":"baixo"}',
        dados,
    ) is None



def test_scroll_down_verification_accepts_observed_after_position():
    assert verificar_resultado_navegador(
        "rolar_pagina",
        '{"direcao":"baixo"}',
        {
            "abas": (
                "Abas abertas: 1\n"
                "Aba ativa: 1\n"
                "Aba 1: Site | https://example.com [ATIVA]"
            ),
            "pagina": "conteudo",
            "scroll": {
                "scroll_y": 900,
                "scroll_height": 3000,
                "viewport_height": 900,
            },
        },
        {
            "direcao": "baixo",
            "scroll_y_antes": 0,
            "scroll_y_depois": 900,
            "scroll_height": 3000,
            "viewport_height": 900,
        },
    ) is True


def test_scroll_down_verification_rejects_unmoved_or_wrong_position():
    assert verificar_resultado_navegador(
        "rolar_pagina",
        '{"direcao":"baixo"}',
        {
            "abas": (
                "Abas abertas: 1\n"
                "Aba ativa: 1\n"
                "Aba 1: Site | https://example.com [ATIVA]"
            ),
            "pagina": "conteudo",
            "scroll": {
                "scroll_y": 0,
                "scroll_height": 3000,
                "viewport_height": 900,
            },
        },
        {
            "direcao": "baixo",
            "scroll_y_antes": 0,
            "scroll_y_depois": 900,
            "scroll_height": 3000,
            "viewport_height": 900,
        },
    ) is False


def test_scroll_to_start_verification_checks_top_position():
    assert verificar_resultado_navegador(
        "rolar_pagina",
        '{"direcao":"inicio"}',
        {
            "abas": (
                "Abas abertas: 1\n"
                "Aba ativa: 1\n"
                "Aba 1: Site | https://example.com [ATIVA]"
            ),
            "pagina": "conteudo",
            "scroll": {
                "scroll_y": 0,
                "scroll_height": 3000,
                "viewport_height": 900,
            },
        },
        {
            "direcao": "inicio",
            "scroll_y_antes": 900,
            "scroll_y_depois": 0,
            "scroll_height": 3000,
            "viewport_height": 900,
        },
    ) is True


def test_scroll_to_end_verification_checks_bottom_position():
    assert verificar_resultado_navegador(
        "rolar_pagina",
        '{"direcao":"fim"}',
        {
            "abas": (
                "Abas abertas: 1\n"
                "Aba ativa: 1\n"
                "Aba 1: Site | https://example.com [ATIVA]"
            ),
            "pagina": "conteudo",
            "scroll": {
                "scroll_y": 2100,
                "scroll_height": 3000,
                "viewport_height": 900,
            },
        },
        {
            "direcao": "fim",
            "scroll_y_antes": 900,
            "scroll_y_depois": 2100,
            "scroll_height": 3000,
            "viewport_height": 900,
        },
    ) is True


def test_open_new_tab_verification_requires_count_and_destination():
    dados = _contexto(
        "Abas abertas: 2\n"
        "Aba ativa: 2\n"
        "Aba 1: Inicio | https://example.com\n"
        "Aba 2: YouTube | https://youtube.com/ [ATIVA]"
    )
    acao = {
        "abas": {
            "quantidade_antes": 1,
            "quantidade_depois": 2,
            "aba_ativa_depois": 2,
            "url_ativa_depois": "https://youtube.com/",
            "depois": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": False},
                {"indice": 2, "titulo": "YouTube", "url": "https://youtube.com/", "ativa": True},
            ],
        }
    }

    assert verificar_resultado_navegador(
        "abrir_nova_aba",
        '{"url":"youtube.com"}',
        dados,
        acao,
    ) is True

    acao["abas"]["quantidade_depois"] = 3
    assert verificar_resultado_navegador(
        "abrir_nova_aba",
        '{"url":"youtube.com"}',
        dados,
        acao,
    ) is False


def test_switch_tab_verification_requires_active_index_and_observed_url():
    dados = _contexto(
        "Abas abertas: 3\n"
        "Aba ativa: 2\n"
        "Aba 1: Inicio | https://example.com\n"
        "Aba 2: Editor | https://example.com/editor [ATIVA]\n"
        "Aba 3: Ajuda | https://example.com/help"
    )
    acao = {
        "abas": {
            "quantidade_antes": 3,
            "quantidade_depois": 3,
            "aba_ativa_depois": 2,
            "url_ativa_depois": "https://example.com/editor",
            "antes": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": True},
                {"indice": 2, "titulo": "Editor", "url": "https://example.com/editor", "ativa": False},
                {"indice": 3, "titulo": "Ajuda", "url": "https://example.com/help", "ativa": False},
            ],
            "depois": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": False},
                {"indice": 2, "titulo": "Editor", "url": "https://example.com/editor", "ativa": True},
                {"indice": 3, "titulo": "Ajuda", "url": "https://example.com/help", "ativa": False},
            ],
        }
    }

    assert verificar_resultado_navegador(
        "trocar_aba",
        '{"indice":2}',
        dados,
        acao,
    ) is True

    assert verificar_resultado_navegador(
        "trocar_aba",
        '{"indice":3}',
        dados,
        acao,
    ) is False


def test_close_tab_verification_requires_decrement_and_new_active_tab():
    dados = _contexto(
        "Abas abertas: 2\n"
        "Aba ativa: 1\n"
        "Aba 1: Inicio | https://example.com [ATIVA]\n"
        "Aba 2: Ajuda | https://example.com/help"
    )
    acao = {
        "abas": {
            "quantidade_antes": 3,
            "quantidade_depois": 2,
            "aba_fechada": 2,
            "aba_ativa_depois": 1,
            "url_ativa_depois": "https://example.com",
            "antes": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": False},
                {"indice": 2, "titulo": "Ajuda", "url": "https://example.com/help", "ativa": True},
                {"indice": 3, "titulo": "Outro", "url": "https://example.com/outro", "ativa": False},
            ],
            "depois": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": True},
                {"indice": 2, "titulo": "Outro", "url": "https://example.com/outro", "ativa": False},
            ],
        }
    }

    assert verificar_resultado_navegador(
        "fechar_aba",
        '{"indice":2}',
        dados,
        acao,
    ) is True

    acao["abas"]["quantidade_depois"] = 1
    assert verificar_resultado_navegador(
        "fechar_aba",
        '{"indice":2}',
        dados,
        acao,
    ) is False

    acao["abas"]["quantidade_depois"] = 2
    acao["abas"]["aba_fechada"] = 3
    assert verificar_resultado_navegador(
        "fechar_aba",
        '{"indice":2}',
        dados,
        acao,
    ) is False



def test_tab_verification_rejects_inconsistent_observed_count():
    dados = _contexto(
        "Abas abertas: 3\n"
        "Aba ativa: 2\n"
        "Aba 1: Inicio | https://example.com\n"
        "Aba 2: Editor | https://example.com/editor [ATIVA]\n"
    )
    acao = {
        "abas": {
            "quantidade_antes": 3,
            "quantidade_depois": 3,
            "aba_ativa_depois": 2,
            "url_ativa_depois": "https://example.com/editor",
            "depois": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": False},
                {"indice": 2, "titulo": "Editor", "url": "https://example.com/editor", "ativa": True},
                {"indice": 3, "titulo": "Ajuda", "url": "https://example.com/help", "ativa": False},
            ],
        }
    }

    assert verificar_resultado_navegador(
        "trocar_aba",
        '{"indice":2}',
        dados,
        acao,
    ) is False


def test_close_last_tab_requires_observed_zero_tabs():
    dados = _contexto("Nenhuma aba aberta no navegador.")
    acao = {
        "abas": {
            "quantidade_antes": 1,
            "quantidade_depois": 0,
            "aba_fechada": 1,
            "aba_ativa_depois": None,
            "url_ativa_depois": None,
            "antes": [
                {"indice": 1, "titulo": "Inicio", "url": "https://example.com", "ativa": True},
            ],
            "depois": [],
        }
    }

    assert verificar_resultado_navegador(
        "fechar_aba",
        '{"indice":1}',
        dados,
        acao,
    ) is True

def test_non_navigational_click_verification_accepts_observed_toggle_state():
    dados = _dados_clique_navegacao()
    dados["clique"].update({
        "navegacao": False,
        "efeito": {
            "controle": {
                "chave": "id:menu",
                "id": "menu",
                "role": "button",
            },
            "sinal": {
                "tipo": "controle",
                "atributo": "aria-expanded",
                "antes": "false",
                "depois": "true",
            },
        },
    })

    pagina = (
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]\n"
        "Elementos flutuantes visiveis: dialogos=0 | menus=1 | listboxes=0\n"
        "Campos e controles visiveis:\n"
        "- tag=button | role=button | nome=Menu | id=menu | chave=id:menu | estado=aria-expanded=true"
    )

    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        {"abas": pagina, "pagina": pagina},
        dados,
    ) is True


def test_non_navigational_click_verification_rejects_wrong_toggle_state():
    dados = _dados_clique_navegacao()
    dados["clique"].update({
        "navegacao": False,
        "efeito": {
            "controle": {"chave": "id:menu"},
            "sinal": {
                "tipo": "controle",
                "atributo": "aria-expanded",
                "antes": "false",
                "depois": "true",
            },
        },
    })

    pagina = (
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]\n"
        "Campos e controles visiveis:\n"
        "- tag=button | role=button | id=menu | chave=id:menu | estado=aria-expanded=false"
    )

    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        {"abas": pagina, "pagina": pagina},
        dados,
    ) is False


def test_non_navigational_click_without_specific_effect_remains_pending():
    dados = _dados_clique_navegacao()
    dados["clique"]["navegacao"] = False
    dados["clique"]["efeito"] = {
        "controle": {"chave": "id:menu"},
    }

    pagina = (
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]\n"
        "Campos e controles visiveis:\n"
        "- tag=button | role=button | id=menu | chave=id:menu"
    )

    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        {"abas": pagina, "pagina": pagina},
        dados,
    ) is None

def test_back_verification_requires_observed_url_change():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Inicio | https://example.com [ATIVA]")
    acao = {"navegacao": {"operacao": "voltar", "url_antes": "https://example.com/a", "url_depois": "https://example.com", "mudou_url": True}}
    assert verificar_resultado_navegador("voltar_pagina", "{}", dados, acao) is True

    acao["navegacao"]["mudou_url"] = False
    assert verificar_resultado_navegador("voltar_pagina", "{}", dados, acao) is False


def test_forward_verification_rejects_mismatched_observed_url():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Outra | https://other.example [ATIVA]")
    acao = {"navegacao": {"operacao": "avancar", "url_depois": "https://example.com", "mudou_url": True}}
    assert verificar_resultado_navegador("avancar_pagina", "{}", dados, acao) is False


def test_reload_verification_requires_new_navigation_time_origin():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]")
    acao = {"navegacao": {"operacao": "recarregar", "url": "https://example.com", "recarregamento_observado": True}}
    assert verificar_resultado_navegador("recarregar_pagina", "{}", dados, acao) is True

    acao["navegacao"]["recarregamento_observado"] = False
    assert verificar_resultado_navegador("recarregar_pagina", "{}", dados, acao) is False


def test_keyboard_f5_requires_navigation_time_origin_change():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]")
    acao = {"tecla": {
        "tecla": "F5",
        "evento_observado": True,
        "estado_antes": {"time_origin": 100.0},
        "estado_depois": {"time_origin": 101.0},
    }}
    assert verificar_resultado_navegador("pressionar_tecla", '{"tecla":"F5"}', dados, acao) is True

    acao["tecla"]["estado_depois"]["time_origin"] = 100.0
    assert verificar_resultado_navegador("pressionar_tecla", '{"tecla":"F5"}', dados, acao) is False


def test_keyboard_escape_requires_observable_overlay_reduction():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]")
    acao = {"tecla": {
        "tecla": "Escape",
        "evento_observado": True,
        "estado_antes": {"dialogs": 1, "menus": 0, "listboxes": 0},
        "estado_depois": {"dialogs": 0, "menus": 0, "listboxes": 0},
    }}
    assert verificar_resultado_navegador("pressionar_tecla", '{"tecla":"Escape"}', dados, acao) is True


def test_keyboard_unknown_effect_remains_inconclusive():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]")
    acao = {"tecla": {
        "tecla": "Delete",
        "evento_observado": True,
        "estado_antes": {"url": "https://example.com", "scroll_y": 100},
        "estado_depois": {"url": "https://example.com", "scroll_y": 100},
    }}
    assert verificar_resultado_navegador("pressionar_tecla", '{"tecla":"Delete"}', dados, acao) is None


def test_keyboard_ctrl_w_requires_before_and_after_tabs():
    dados = _contexto("Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]")
    acao = {"tecla": {
        "tecla": "Ctrl+W",
        "evento_observado": True,
        "estado_antes": {},
        "estado_depois": {},
        "abas_antes": [
            {"indice": 1, "url": "https://example.com", "ativa": True},
            {"indice": 2, "url": "https://example.com/2", "ativa": False},
        ],
        "abas_depois": [
            {"indice": 1, "url": "https://example.com", "ativa": True},
        ],
    }}
    assert verificar_resultado_navegador("pressionar_tecla", '{"tecla":"Ctrl+W"}', dados, acao) is True

def test_non_navigational_click_verification_accepts_aria_checked():
    dados = _dados_clique_navegacao()
    dados["clique"]["navegacao"] = False
    dados["clique"]["efeito"] = {
        "controle": {"chave": "id:check", "id": "check"},
        "sinal": {
            "tipo": "controle",
            "atributo": "aria-checked",
            "antes": "false",
            "depois": "true",
        },
    }
    pagina = _contexto(
        "Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]"
    )
    pagina["pagina"] = (
        "Campos e controles visiveis:\n"
        "- tag=button | nome=Opcao | id=check | chave=id:check | estado=aria-checked=true"
    )
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Opcao","indice":1}',
        pagina,
        dados,
    ) is True


def test_non_navigational_click_verification_accepts_native_details_open_state():
    dados = _dados_clique_navegacao()
    dados["clique"]["navegacao"] = False
    dados["clique"]["efeito"] = {
        "controle": {"chave": "tag:summary:ajuda"},
        "sinal": {
            "tipo": "controle",
            "atributo": "details-open",
            "antes": False,
            "depois": True,
        },
    }
    pagina = _contexto(
        "Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]"
    )
    pagina["pagina"] = (
        "Campos e controles visiveis:\n"
        "- tag=summary | nome=Ajuda | chave=tag:summary:ajuda | estado=details-open=true"
    )
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Ajuda","indice":1}',
        pagina,
        dados,
    ) is True


def test_non_navigational_click_verification_accepts_alertdialog_and_popover_effect():
    dados = _dados_clique_navegacao()
    dados["clique"]["navegacao"] = False
    dados["clique"]["efeito"] = {
        "controle": {"chave": "id:abrir"},
        "pagina_antes": {"popovers": 0},
        "pagina_depois": {"popovers": 1},
        "sinal": {"tipo": "pagina", "alvo": "popovers", "antes": 0, "depois": 1},
    }
    pagina = _contexto(
        "Abas abertas: 1\nAba ativa: 1\nAba 1: Site | https://example.com [ATIVA]"
    )
    pagina["pagina"] = (
        "Campos e controles visiveis:\n"
        "- tag=button | role=button | nome=Abrir | id=abrir | chave=id:abrir\n"
        "Elementos flutuantes visiveis: dialogos=1 | menus=0 | listboxes=0 | popovers=1 | details_abertos=0"
    )
    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Abrir","indice":1}',
        pagina,
        dados,
    ) is True


def test_browser_navigation_verification_accepts_final_url_after_redirect():
    contexto = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Login | https://example.com/dashboard [ATIVA]"
    )
    acao = {
        "navegacao": {
            "operacao": "navegar",
            "url_solicitada": "https://example.com",
            "url_antes": "about:blank",
            "url_depois": "https://example.com/dashboard",
            "mudou_url": True,
        }
    }

    assert verificar_resultado_navegador(
        "navegar_navegador",
        '{"url":"https://example.com","modo":"visivel"}',
        contexto,
        acao,
    ) is True


def test_browser_navigation_verification_stays_inconclusive_without_structured_evidence():
    contexto = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]"
    )
    assert verificar_resultado_navegador(
        "navegar_navegador",
        '{"url":"https://example.com","modo":"visivel"}',
        contexto,
        None,
    ) is None


def test_non_navigational_click_verification_accepts_dom_only_control_change():
    compromisso_before = "1111111111111111"
    compromisso_after = "2222222222222222"
    contexto = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]\n"
        "Campos e controles visiveis:\n"
        f"- tag=button | role=button | nome=Menu | chave=id:menu | dom-fingerprint={compromisso_after}"
    )
    acao = {
        "clique": {
            "navegacao": False,
            "efeito": {
                "controle": {
                    "chave": "id:menu",
                    "dom_fingerprint": compromisso_before,
                },
                "pagina_antes": {},
                "pagina_depois": {},
                "sinal": {
                    "tipo": "controle",
                    "atributo": "domFingerprint",
                    "antes": compromisso_before,
                    "depois": compromisso_after,
                },
            },
        }
    }

    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        contexto,
        acao,
    ) is True


def test_dom_only_click_verification_rejects_unchanged_fingerprint():
    contexto = _contexto(
        "Abas abertas: 1\n"
        "Aba ativa: 1\n"
        "Aba 1: Site | https://example.com [ATIVA]\n"
        "Campos e controles visiveis:\n"
        "- tag=button | role=button | nome=Menu | chave=id:menu | dom-fingerprint=1111111111111111"
    )
    acao = {
        "clique": {
            "navegacao": False,
            "efeito": {
                "controle": {"chave": "id:menu"},
                "sinal": {
                    "tipo": "controle",
                    "atributo": "domFingerprint",
                    "antes": "1111111111111111",
                    "depois": "2222222222222222",
                },
            },
        }
    }

    assert verificar_resultado_navegador(
        "clicar_elemento",
        '{"alvo":"Menu","indice":1}',
        contexto,
        acao,
    ) is False
