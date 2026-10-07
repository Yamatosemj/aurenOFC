from __future__ import annotations

import pytest

from core.permission_manager import PermissionLevel, PermissionManager


class _RecordingConfirmationChannel:
    def __init__(self, answer: bool):
        self.answer = answer
        self.requests = []

    def confirmar(self, request):
        self.requests.append(request)
        return self.answer

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

    contexto_windows = {
        "_key_context_ok": True,
        "_key_context": {
            "ambiente": "windows",
            "context_known": True,
        },
    }
    for tecla in ("Tab", "Escape", "Control+L", "Alt+Left"):
        args = {"tecla": tecla, **contexto_windows}
        esperado = PermissionLevel.CONFIRM if tecla in {"Control+L", "Alt+Left"} else PermissionLevel.AUTO
        assert _nivel("pressionar_tecla_windows", args) == esperado

    assert _nivel(
        "pressionar_tecla_windows",
        {"tecla": "Tab"},
    ) == PermissionLevel.CONFIRM

    for tecla in ("Delete", "Control+W", "Ctrl+W", "Alt+F4", "Enter", "F5"):
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


def test_clique_no_navegador_usa_allowlist_e_evidencia_estrutural():
    assert _nivel("clicar_elemento", {"alvo": "Pesquisar", "indice": 1}) == PermissionLevel.CONFIRM
    assert _nivel("clicar_elemento", {"alvo": "Pesquisar videos", "indice": 1}) == PermissionLevel.CONFIRM
    assert _nivel("clicar_elemento", {"alvo": "Comprar", "indice": 1}) == PermissionLevel.CONFIRM
    assert _nivel("clicar_elemento", _browser_click_args(tag="button", role="button", type="button")) == PermissionLevel.AUTO
    assert _nivel(
        "clicar_elemento",
        _browser_click_args(
            tag="a",
            role="link",
            type="",
            href="/delete-account",
        ),
    ) == PermissionLevel.CONFIRM


def test_navegacao_do_navegador_e_allowlistada():
    assert _nivel(
        "navegar_navegador",
        {"url": "https://example.com", "modo": "visivel"},
    ) == PermissionLevel.AUTO
    assert _nivel("voltar_pagina") == PermissionLevel.AUTO
    assert _nivel("avancar_pagina") == PermissionLevel.AUTO
    assert _nivel("recarregar_pagina") == PermissionLevel.CONFIRM


def test_controle_de_abas_trata_fechamento_como_acao_de_risco():
    assert _nivel("abrir_nova_aba", {"url": "", "modo": "visivel"}) == PermissionLevel.AUTO
    assert _nivel("abrir_nova_aba", {"url": "https://example.com/docs", "modo": "visivel"}) == PermissionLevel.AUTO
    assert _nivel("abrir_nova_aba", {"url": "https://example.com/logout", "modo": "visivel"}) == PermissionLevel.CONFIRM
    assert _nivel("abrir_nova_aba", {"url": "javascript:doSomething()", "modo": "visivel"}) == PermissionLevel.CONFIRM
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


def _browser_click_args(**evidencia):
    return {
        "alvo": "Pesquisar",
        "indice": 1,
        "_browser_click_preflight_ok": True,
        "_browser_click_preflight": evidencia,
    }


def test_safe_browser_click_requires_structural_preflight():
    manager = PermissionManager()
    nivel, _ = manager.nivel_da_acao(
        "clicar_elemento",
        {"alvo": "Pesquisar", "indice": 1},
    )
    assert nivel == PermissionLevel.CONFIRM


def test_safe_browser_click_allows_plain_button_with_structural_evidence():
    manager = PermissionManager()
    nivel, motivo = manager.nivel_da_acao(
        "clicar_elemento",
        _browser_click_args(tag="button", role="button", type="button", href=""),
    )
    assert nivel == PermissionLevel.AUTO
    assert "estrutura real" in motivo


@pytest.mark.parametrize(
    "evidencia",
    [
        {"tag": "button", "role": "button", "type": "submit", "href": ""},
        {"tag": "button", "role": "button", "type": "button", "href": "", "onclick": "submit()"},
        {"tag": "a", "role": "link", "type": "", "href": "javascript:submit()"},
        {"tag": "a", "role": "link", "type": "", "href": "/checkout", "target": "_blank"},
        {"tag": "a", "role": "link", "type": "", "href": "/send", "form": {"method": "post", "action": "/send"}},
        {"tag": "a", "role": "link", "type": "", "href": "/arquivo", "download": True},
    ],
)
def test_safe_click_is_elevated_for_risky_structural_evidence(evidencia):
    manager = PermissionManager()
    nivel, _ = manager.nivel_da_acao(
        "clicar_elemento",
        _browser_click_args(**evidencia),
    )
    assert nivel == PermissionLevel.CONFIRM


def test_denied_or_blocked_counted_actions_do_not_consume_budget():
    channel = _RecordingConfirmationChannel(False)
    manager = PermissionManager(max_actions=2, confirmation_channel=channel)
    assert manager.autorizar("fechar_aba", {"indice": 2})[0] is False
    assert manager.actions_attempted == 0

    manager.policy["memory.write"] = PermissionLevel.BLOCKED
    assert manager.autorizar("salvar_memoria_persistente", {"chave": "x", "valor": "y"})[0] is False
    assert manager.actions_attempted == 0


def test_authorized_auto_and_confirmed_actions_consume_budget_once():
    manager = PermissionManager(max_actions=2, confirmation_channel=_RecordingConfirmationChannel(True))

    assert manager.autorizar("navegar_navegador", {"url": "https://example.com", "modo": "visivel"})[0] is True
    assert manager.actions_attempted == 1

    assert manager.autorizar("fechar_aba", {"indice": 2})[0] is True
    assert manager.actions_attempted == 2


@pytest.mark.parametrize("nome_ferramenta", ["recarregar_pagina", "pressionar_tecla"])
def test_browser_reload_requires_confirmation_even_when_named_safe(nome_ferramenta):
    manager = PermissionManager()

    if nome_ferramenta == "recarregar_pagina":
        args = {}
    else:
        args = {"tecla": "F5"}

    nivel, motivo = manager.nivel_da_acao(nome_ferramenta, args)

    assert nivel == PermissionLevel.CONFIRM
    assert "repetir" in motivo.lower() or "confirmacao" in motivo.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/logout",
        "https://example.com/checkout",
        "https://example.com/account/delete",
        "https://example.com/payment/confirm",
    ],
)
def test_navigation_to_potentially_persistent_action_requires_confirmation(url):
    manager = PermissionManager()
    nivel, _ = manager.nivel_da_acao(
        "navegar_navegador",
        {"url": url, "modo": "visivel"},
    )
    assert nivel == PermissionLevel.CONFIRM


def test_navigation_to_normal_readonly_destination_remains_auto():
    manager = PermissionManager()
    nivel, _ = manager.nivel_da_acao(
        "navegar_navegador",
        {"url": "https://example.com/search?q=auren", "modo": "visivel"},
    )
    assert nivel == PermissionLevel.AUTO


def test_no_progress_guard_covers_repeated_browser_click_and_keypress():
    manager = PermissionManager(max_no_progress_repeats=3)
    argumentos_clique = {"alvo": "Pesquisar", "indice": 1}
    argumentos_tecla = {"tecla": "ArrowDown"}

    for _ in range(3):
        manager.registrar_resultado(True, "clicar_elemento", argumentos_clique)

    permitido, motivo = manager.autorizar("clicar_elemento", argumentos_clique)
    assert permitido is False
    assert "evid" in motivo.lower() and "progresso" in motivo.lower()

    manager.iniciar_tarefa()
    for _ in range(3):
        manager.registrar_resultado(True, "pressionar_tecla", argumentos_tecla)

    permitido, motivo = manager.autorizar("pressionar_tecla", argumentos_tecla)
    assert permitido is False
    assert "evid" in motivo.lower() and "progresso" in motivo.lower()


def test_browser_safe_key_is_context_sensitive_to_application():
    assert _nivel(
        "pressionar_tecla_windows",
        {
            "tecla": "Control+L",
            "_key_context_ok": True,
            "_key_context": {"ambiente": "windows", "context_known": True},
        },
    ) == PermissionLevel.CONFIRM

    assert _nivel(
        "pressionar_tecla",
        {
            "tecla": "Control+L",
            "_key_context_ok": True,
            "_key_context": {"ambiente": "browser", "context_known": True},
        },
    ) == PermissionLevel.AUTO
