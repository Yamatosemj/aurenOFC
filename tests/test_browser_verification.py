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
            "depois": [],
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
            "depois": [],
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
            "depois": [],
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

