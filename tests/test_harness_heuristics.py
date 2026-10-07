from __future__ import annotations

from core.harness_heuristics import _pode_encerrar_localmente


def _decide(objetivo, resultados, *, vision=False, multitab=False):
    return _pode_encerrar_localmente(
        objetivo,
        resultados,
        vision_reobserve_pending=vision,
        visual_mutating_tools={
            "clicar_elemento",
            "clicar_elemento_windows",
        },
        terminal_result_tools={
            "obter_status_windows",
            "listar_abas",
            "consultar_memoria_persistente",
            "definir_volume_windows",
        },
        multitab_concluida=lambda *_: multitab,
    )


def test_nao_conclui_com_reobservacao_visual_pendente():
    assert _decide(
        "clique no botao e depois verifique a tela",
        [{"ferramenta": "clicar_elemento", "sucesso": True}],
        vision=True,
    ) is False


def test_tarefa_visual_composta_exige_reobservacao_apos_mutacao():
    assert _decide(
        "olhe a tela e clique no botao depois confirme",
        [{"ferramenta": "clicar_elemento", "sucesso": True}],
    ) is False


def test_multitab_concluida_pode_encerrar_localmente():
    assert _decide(
        "coloque os destinos nas duas abas",
        [{"ferramenta": "listar_abas", "sucesso": True}],
        multitab=True,
    ) is True


def test_ultima_acao_solicitada_so_conclui_com_todas_as_ferramentas_bem_sucedidas():
    resultados = [
        {"ferramenta": "abrir_navegador", "sucesso": True},
        {"ferramenta": "clicar_elemento", "sucesso": True},
    ]
    assert _decide("clique em salvar", resultados) is True


def test_ultima_acao_solicitada_nao_conclui_com_falha_anterior():
    resultados = [
        {"ferramenta": "abrir_navegador", "sucesso": False},
        {"ferramenta": "clicar_elemento", "sucesso": True},
    ]
    assert _decide("clique em salvar", resultados) is False


def test_ferramenta_terminal_de_leitura_pode_concluir_consulta_simples():
    assert _decide(
        "qual o status do windows",
        [{"ferramenta": "obter_status_windows", "sucesso": True}],
    ) is True


def test_ferramenta_terminal_de_leitura_nao_conclui_acao_explicita():
    assert _decide(
        "abra o navegador",
        [{"ferramenta": "obter_status_windows", "sucesso": True}],
    ) is False


def test_ferramenta_nao_terminal_nao_conclui():
    assert _decide(
        "faça isso",
        [{"ferramenta": "abrir_navegador", "sucesso": True}],
    ) is False


def test_multiplas_ferramentas_sem_ultima_acao_nao_concluem_automaticamente():
    assert _decide(
        "faça uma coisa",
        [
            {"ferramenta": "obter_status_windows", "sucesso": True},
            {"ferramenta": "consultar_memoria_persistente", "sucesso": True},
        ],
    ) is False
