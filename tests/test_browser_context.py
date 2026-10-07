from __future__ import annotations

from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_result import ToolResult
from tools import browser, browser_context


class _FakePage:
    def evaluate(self, _script):
        return {
            "scroll_y": 900,
            "scroll_height": 3000,
            "viewport_height": 900,
        }


def test_browser_context_combines_tabs_and_active_page(monkeypatch):
    monkeypatch.setattr(
        browser,
        "listar_abas",
        lambda: "Abas abertas: 2\nAba ativa: 2",
    )
    monkeypatch.setattr(
        browser,
        "ler_pagina",
        lambda foco: f"Titulo: YouTube\nFoco da leitura: {foco}",
    )

    result = browser_context.obter_contexto_navegador("video de teste")

    assert result.ok is True
    assert result.tool_name == "obter_contexto_navegador"
    assert result.conteudo_nao_confiavel is True
    assert "Abas abertas: 2" in result.message
    assert "Titulo: YouTube" in result.message
    assert result.data["foco"] == "video de teste"
    assert result.data["scroll"] == {
        "scroll_y": 900,
        "scroll_height": 3000,
        "viewport_height": 900,
    }


def test_browser_context_is_read_only_and_untrusted():
    result = ToolResult.success(
        "conteudo externo",
        tool_name="obter_contexto_navegador",
        conteudo_nao_confiavel=True,
    )
    manager = PermissionManager()
    manager.registrar_fonte_nao_confiavel("obter_contexto_navegador")

    nivel, motivo = manager.nivel_da_acao(
        "clicar_elemento",
        {"alvo": "Comprar", "indice": 1},
    )

    assert result.conteudo_nao_confiavel is True
    assert nivel == PermissionLevel.CONFIRM
    assert "conteudo nao confiavel" in motivo
