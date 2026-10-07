from __future__ import annotations

from core.permission_manager import PermissionLevel, PermissionManager


def _nivel(nome: str, argumentos: dict | None = None):
    manager = PermissionManager()
    return manager.nivel_da_acao(nome, argumentos or {})[0]


def test_toda_capacidade_auto_tem_justificativa_escrita():
    auto = {
        capacidade
        for capacidade, nivel in PermissionManager.CAPABILITY_POLICY.items()
        if nivel == PermissionLevel.AUTO
    }
    assert auto == set(PermissionManager.AUTO_CAPABILITY_JUSTIFICATIONS)


def test_controle_de_janela_e_allowlistado():
    assert _nivel("focar_janela_windows", {"alvo": "Bloco de Notas"}) == PermissionLevel.AUTO
    assert _nivel("minimizar_janela_windows", {"alvo": "Bloco de Notas"}) == PermissionLevel.AUTO
    assert _nivel("maximizar_janela_windows", {"alvo": "Bloco de Notas"}) == PermissionLevel.AUTO
    assert _nivel("mover_janela_windows", {"alvo": "Bloco de Notas", "x": 0, "y": 0}) == PermissionLevel.AUTO
    assert _nivel("redimensionar_janela_windows", {"alvo": "Bloco de Notas", "largura": 800, "altura": 600}) == PermissionLevel.AUTO
    assert _nivel("restaurar_janela_windows", {"alvo": "Bloco de Notas"}) == PermissionLevel.AUTO
    assert _nivel("fechar_janela_windows", {"alvo": "Bloco de Notas"}) == PermissionLevel.CONFIRM


def test_entrada_global_tem_allowlist_de_acoes_e_teclas():
    assert _nivel("mover_mouse_windows", {"x": 100, "y": 100}) == PermissionLevel.AUTO

    for nome, argumentos in (
        ("clicar_mouse_windows", {"x": 100, "y": 100, "botao": "esquerdo", "descricao": "botao"}),
        (
            "arrastar_mouse_windows",
            {
                "x_inicial": 100,
                "y_inicial": 100,
                "x_final": 200,
                "y_final": 200,
                "botao": "esquerdo",
                "duracao_ms": 300,
                "descricao": "arraste",
            },
        ),
    ):
        assert _nivel(nome, argumentos) == PermissionLevel.CONFIRM

    for tecla in ("Tab", "Escape", "Control+L", "F5", "Alt+Left"):
        assert _nivel("pressionar_tecla_windows", {"tecla": tecla}) == PermissionLevel.AUTO

    for tecla in ("Delete", "Control+W", "Ctrl+W", "Alt+F4", "Enter"):
        assert _nivel("pressionar_tecla_windows", {"tecla": tecla}) == PermissionLevel.CONFIRM


def test_coordenada_windows_nao_verificada_nao_pode_ser_auto():
    assert _nivel(
        "clicar_mouse_windows",
        {
            "x": 400,
            "y": 300,
            "botao": "esquerdo",
            "descricao": "coordenada sem contexto verificado",
            "coordinate_space": "windows",
        },
    ) == PermissionLevel.CONFIRM


def test_controle_ui_exige_confirmacao_salvo_preenchimento_seguro():
    assert _nivel(
        "preencher_elemento_windows",
        {
            "alvo_janela": "Chrome",
            "alvo": "pesquisa",
            "texto": "auren",
            "indice": 1,
        },
    ) == PermissionLevel.AUTO

    assert _nivel(
        "preencher_elemento_windows",
        {
            "alvo_janela": "Chrome",
            "alvo": "email",
            "texto": "victor@example.com",
            "indice": 1,
        },
    ) == PermissionLevel.CONFIRM

    assert _nivel(
        "preencher_elemento_windows",
        {
            "alvo_janela": "Chrome",
            "alvo": "senha",
            "texto": "segredo",
            "indice": 1,
        },
    ) == PermissionLevel.CONFIRM

    for nome in (
        "clicar_elemento_windows",
        "alternar_elemento_windows",
        "selecionar_elemento_windows",
    ):
        assert _nivel(
            nome,
            {"alvo_janela": "Config", "alvo": "Opcao", "indice": 1},
        ) == PermissionLevel.CONFIRM


def test_clique_no_navegador_usa_allowlist_exata():
    assert _nivel("clicar_elemento", {"alvo": "Pesquisar", "indice": 1}) == PermissionLevel.AUTO
    assert _nivel("clicar_elemento", {"alvo": "Pesquisar videos", "indice": 1}) == PermissionLevel.CONFIRM
    assert _nivel("clicar_elemento", {"alvo": "Comprar", "indice": 1}) == PermissionLevel.CONFIRM


def test_navegacao_do_navegador_e_allowlistada():
    assert _nivel(
        "navegar_navegador",
        {"url": "https://example.com", "modo": "visivel"},
    ) == PermissionLevel.AUTO
    assert _nivel("voltar_pagina") == PermissionLevel.AUTO
    assert _nivel("avancar_pagina") == PermissionLevel.AUTO
    assert _nivel("recarregar_pagina") == PermissionLevel.AUTO


def test_controle_de_abas_trata_fechamento_como_acao_de_risco():
    assert _nivel("abrir_nova_aba", {"url": "", "modo": "visivel"}) == PermissionLevel.AUTO
    assert _nivel("trocar_aba", {"indice": 2}) == PermissionLevel.AUTO
    assert _nivel("fechar_aba", {"indice": 2}) == PermissionLevel.CONFIRM


def test_untrusted_source_confirmation_is_consumed_after_approved_counted_action():
    requests = []

    class FakeChannel:
        def confirmar(self, request):
            requests.append(request)
            return True

    manager = PermissionManager(confirmation_channel=FakeChannel())
    manager.iniciar_tarefa()
    manager.registrar_fonte_nao_confiavel("ler_pagina")

    permitido, _ = manager.autorizar(
        "navegar_navegador",
        {"url": "https://example.com", "modo": "visivel"},
    )
    assert permitido is True
    assert len(requests) == 1
    assert "conteudo nao confiavel" in requests[0].reason
    assert manager.fonte_nao_confiavel_pendente is None

    permitido, _ = manager.autorizar(
        "navegar_navegador",
        {"url": "https://example.com/2", "modo": "visivel"},
    )
    assert permitido is True
    assert len(requests) == 1


def test_untrusted_source_confirmation_is_consumed_after_denial():
    requests = []

    class FakeChannel:
        def confirmar(self, request):
            requests.append(request)
            return False

    manager = PermissionManager(confirmation_channel=FakeChannel())
    manager.iniciar_tarefa()
    manager.registrar_fonte_nao_confiavel("ler_pagina")

    permitido, motivo = manager.autorizar(
        "fechar_aba",
        {"indice": 2},
    )
    assert permitido is False
    assert motivo == "Usuario negou a acao."
    assert len(requests) == 1
    assert manager.fonte_nao_confiavel_pendente is None


def test_untrusted_source_never_overrides_blocked_policy():
    manager = PermissionManager()
    manager.policy["memory.write"] = PermissionLevel.BLOCKED
    manager.registrar_fonte_nao_confiavel("ler_pagina")

    permitido, motivo = manager.autorizar(
        "salvar_memoria_persistente",
        {"chave": "teste", "valor": "valor"},
    )

    assert permitido is False
    assert "bloqueada" in motivo.lower()
    assert manager.fonte_nao_confiavel_pendente == "ler_pagina"
