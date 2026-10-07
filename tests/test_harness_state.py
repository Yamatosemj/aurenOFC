from core.harness_state import _montar_estado


def test_browser_verification_state_names_the_action_and_required_evidence():
    result = _montar_estado(
        "abra o youtube e verifique",
        [],
        [],
        incluir_contexto=False,
        contexto_tarefa="",
        vision_reobserve_pending=False,
        browser_verification_pending=True,
        browser_verification_action="navegar_navegador",
        max_history_items=2,
        max_state_chars=5000,
        texto_seguro=lambda value, _limit: value,
    )

    assert "navegar_navegador" in result
    assert "titulo" in result.lower()
    assert "url" in result.lower()
    assert "obter_contexto_navegador" in result


def test_browser_verification_state_for_scroll_requests_expected_content():
    result = _montar_estado(
        "role ate a secao de comentarios e verifique",
        [],
        [],
        incluir_contexto=False,
        contexto_tarefa="",
        vision_reobserve_pending=False,
        browser_verification_pending=True,
        browser_verification_action="rolar_pagina",
        max_history_items=2,
        max_state_chars=5000,
        texto_seguro=lambda value, _limit: value,
    )

    assert "rolar_pagina" in result
    assert "conteudo esperado" in result.lower()
