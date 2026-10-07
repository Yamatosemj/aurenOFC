from core.browser_verification import verificar_resultado_navegador


def _contexto(pagina):
    return {
        "abas": (
            "Abas abertas: 1\n"
            "Aba ativa: 1\n"
            "Aba 1: Editor | https://example.com [ATIVA]"
        ),
        "pagina": pagina,
    }


def test_fill_verification_accepts_matching_visible_value():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Nome","texto":"Victor","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | role=textbox | nome=Nome | valor=Victor"
        ),
    ) is True


def test_fill_verification_rejects_wrong_visible_value():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Nome","texto":"Victor","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | role=textbox | nome=Nome | valor=Maria"
        ),
    ) is False


def test_fill_verification_does_not_infer_redacted_secret():
    assert verificar_resultado_navegador(
        "preencher_elemento",
        '{"alvo":"Senha","texto":"segredo","indice":1}',
        _contexto(
            "Campos e controles visiveis:\n"
            "- tag=input | nome=Senha | valor=[REDACTED]"
        ),
    ) is None
