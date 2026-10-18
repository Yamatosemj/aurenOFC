import json
from types import SimpleNamespace

import pytest

from core.browser_verification import verificar_resultado_navegador
from core.permission_manager import PermissionManager
from core.tool_result import ToolResult, from_legacy
from tests.test_harness_tools import _TaskManager, _item, _rodada_com_falhas
from core.harness_tools import _executar_chamadas_rodada
from tools import applications, browser, browser_context, dispatcher, windows_window


@pytest.mark.parametrize("tool,method", [("focar_janela_windows", "SetForegroundWindow"),
                                        ("fechar_janela_windows", "PostMessageW")])
def test_aud002_liv003_window_refusal_is_failure(monkeypatch, tool, method):
    monkeypatch.setattr(windows_window, "_encontrar_janela_windows", lambda _: (42, "Ficticia"))
    monkeypatch.setattr(windows_window, "_user32", lambda: SimpleNamespace(
        ShowWindow=lambda *a: True, SetForegroundWindow=lambda *a: False,
        PostMessageW=lambda *a: False))
    result = from_legacy(getattr(windows_window, tool)("Ficticia"), tool_name=tool)
    assert not result.ok
    assert result.error_code != "legacy_text_error"


def test_aud002_shortcut_failure_is_structured(monkeypatch, tmp_path):
    monkeypatch.setattr(applications, "encontrar_aplicativo", lambda _: None)
    monkeypatch.setattr(applications, "procurar_atalho", lambda _: tmp_path / "app.lnk")
    def fail(*a):
        raise OSError("erro ficticio")
    monkeypatch.setattr(applications.os, "startfile", fail)
    assert not from_legacy(applications.abrir_programa("Ficticio")).ok


def test_aud003_different_private_value_does_not_recover_failure():
    pending = set()
    args = lambda text: json.dumps({"alvo": "Pesquisa", "texto": text, "indice": 1})
    result = _rodada_com_falhas(
        [_item("preencher_elemento", "a", args("ALFA_FICTICIO")),
         _item("preencher_elemento", "b", args("BETA_FICTICIO"))],
        [ToolResult.failure("falha"), ToolResult.success("ok")], pending)
    assert result[2] is True
    assert len(pending) == 1
    assert "ALFA_FICTICIO" not in repr(pending)


def test_aud003_json_order_does_not_change_recovery_identity():
    result = _rodada_com_falhas(
        [_item("preencher_elemento", "a", '{"alvo":"Pesquisa","texto":"ALFA","indice":1}'),
         _item("preencher_elemento", "b", '{"indice":1, "texto":"ALFA", "alvo":"Pesquisa"}')],
        [ToolResult.failure("falha"), ToolResult.success("ok")], set())
    assert result[2] is False


def test_aud004_harness_verifies_original_value_without_logging_it():
    state, logs, history = {}, [], []
    replies = iter([ToolResult.success("feito"), ToolResult.success("contexto", data={
        "abas": "Aba ativa: 1\nAba 1: Editor | https://example.invalid [ATIVA]",
        "pagina": "- tag=input | nome=Pesquisa | valor=ALFA_FICTICIO"})])
    _executar_chamadas_rodada(
        [_item("preencher_elemento", "a", '{"alvo":"Pesquisa","texto":"ALFA_FICTICIO","indice":1}'),
         _item("obter_contexto_navegador", "b")],
        historico=history, task_manager=_TaskManager(), task_id="ficticio", rodada=1,
        executar_ferramenta=lambda _: next(replies), trace=None,
        vision_state_mutating_tools=set(), vision_reobserve_pending=False,
        falha_nao_recuperada=False, max_tool_result_chars=2200,
        get_active_vision_geometry=lambda: None, clear_active_vision_geometry=lambda: None,
        write_log=lambda event, **kw: logs.append((event, kw)),
        browser_verification_state=state, browser_state_mutating_tools={"preencher_elemento"},
        browser_verifier=verificar_resultado_navegador)
    assert state["pending"] is False
    assert "ALFA_FICTICIO" not in history[0]["argumentos"]
    assert "ALFA_FICTICIO" not in logs[0][1]["argumentos"]


@pytest.mark.parametrize("value,index,expected", [("ALFABETO", 1, False), ("ALFA", 2, False)])
def test_aud004_value_and_index_must_match_exactly(value, index, expected):
    result = verificar_resultado_navegador("preencher_elemento", json.dumps({
        "alvo": "Pesquisa", "texto": "ALFA", "indice": index}), {
        "abas": "Aba ativa: 1\nAba 1: Editor | https://example.invalid [ATIVA]",
        "pagina": f"- tag=input | nome=Pesquisa | valor={value}\n- tag=input | nome=Pesquisa | valor=OUTRO"})
    assert result is expected


@pytest.mark.parametrize("failure", [ToolResult.failure("erro ficticio"), "Nao consegui ler a pagina: falha ficticia"])
def test_aud025_failed_page_is_not_successful_context(monkeypatch, failure):
    monkeypatch.setattr(browser, "listar_abas", lambda: "Abas abertas: 1")
    monkeypatch.setattr(browser, "ler_pagina", lambda _: failure)
    monkeypatch.setattr(browser, "obter_pagina", lambda: SimpleNamespace(evaluate=lambda _: {}))
    result = browser_context.obter_contexto_navegador()
    assert not result.ok
    assert result.data["abas"] == "Abas abertas: 1"
    assert result.conteudo_nao_confiavel


@pytest.mark.parametrize("tool,args", [
    ("salvar_memoria_persistente", {"chave": "fato", "valor": "ficticio", "categoria": "geral"}),
    ("esquecer_memoria_persistente", {"chave": "fato"}),
])
def test_aud028_memory_refusal_reaches_dispatcher(tool, args):
    store = SimpleNamespace(salvar=lambda *a: {"ok": False, "erro": "recusa ficticia"},
                            esquecer=lambda *a: {"ok": False, "erro": "recusa ficticia"})
    manager = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: True))
    result = dispatcher.executar_ferramenta(SimpleNamespace(name=tool, arguments=json.dumps(args)), manager, store)
    assert not result.ok
    assert "recusa ficticia" in result.message
