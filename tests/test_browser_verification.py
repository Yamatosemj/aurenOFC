from core.browser_verification import verificar_resultado_navegador


def _contexto(abas):
    return {"abas": abas, "pagina": "conteudo"}


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
