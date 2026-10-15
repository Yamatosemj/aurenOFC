"""Regressao da auditoria: erros de processo nao podem virar sucesso por texto.

So mocks: nao chama tasklist/taskkill reais, nao inicia Auren nem usa API.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.tool_result import ToolResult, from_legacy
from tools import windows_processes as processes


def _windows(monkeypatch, *, pid=9999):
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt", getpid=lambda: pid))


def _result(value, *, ok: bool, code: str | None, tool: str):
    assert isinstance(value, ToolResult)
    assert value.ok is ok
    assert value.error_code == code
    assert value.tool_name == tool
    converted = from_legacy(value, tool_name=tool)
    assert converted.ok is ok
    assert converted.error_code == code
    if not ok:
        assert converted.as_dict()["ok"] is False
        assert '"ok":false' in converted.for_model()
    else:
        assert converted.for_model() == value.message


@pytest.mark.parametrize("operation,tool", [
    (lambda: processes.listar_processos_windows(), "listar_processos_windows"),
    (lambda: processes.encerrar_processo_windows(pid=123), "encerrar_processo_windows"),
])
def test_platform_failure_is_structured(monkeypatch, operation, tool):
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="posix"))
    _result(operation(), ok=False, code="windows_only", tool=tool)


def test_process_list_nonzero_exit_is_failure_regardless_of_error_language(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(
        processes.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=5, stdout="", stderr="Zugriff verweigert"),
    )
    _result(
        processes.listar_processos_windows("steam"),
        ok=False, code="process_list_failed", tool="listar_processos_windows",
    )


def test_process_list_exception_is_failure_even_with_unknown_wording(monkeypatch):
    _windows(monkeypatch)
    def explode(*a, **kw):
        raise RuntimeError("WERT_FREMDE_MELDUNG")
    monkeypatch.setattr(processes.subprocess, "run", explode)
    _result(
        processes.listar_processos_windows(),
        ok=False, code="process_list_exception", tool="listar_processos_windows",
    )


def test_process_list_success_retains_plain_text_and_empty_filter_semantics(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(
        processes.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout='"steam.exe","19380","Console","1","12.000 K"\n'
                   '"explorer.exe","1234","Console","1","11.000 K"\n',
            stderr="",
        ),
    )
    found = processes.listar_processos_windows("steam")
    _result(found, ok=True, code=None, tool="listar_processos_windows")
    assert found.message == "Processos encontrados: 1\nsteam.exe | PID 19380 | memoria 12.000 K"
    none = processes.listar_processos_windows("naoexiste")
    _result(none, ok=True, code=None, tool="listar_processos_windows")
    assert "Nenhum processo corresponde" in none.message


def test_process_list_empty_is_valid_success(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(
        processes.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    value = processes.listar_processos_windows()
    _result(value, ok=True, code=None, tool="listar_processos_windows")
    assert value.message == "Nenhum processo foi encontrado."


@pytest.mark.parametrize("args,code", [
    ({}, "process_target_missing"),
    ({"pid": "texto"}, "pid_invalid"),
    ({"pid": -1}, "pid_invalid"),
    ({"nome": "chrome*"}, "process_wildcard_rejected"),
    ({"nome": "explorer.exe"}, "protected_process_blocked"),
    ({"pid": 9999}, "self_process_blocked"),
    ({"pid": 123, "nome": "chrome.exe", "forcar": "sim"}, "force_invalid"),
    ({"pid": 123, "nome": "", "forcar": True}, "force_requires_pid_and_name"),
])
def test_process_termination_rejects_invalid_or_dangerous_calls_without_taskkill(monkeypatch, args, code):
    _windows(monkeypatch)
    def forbidden(*a, **kw):
        raise AssertionError("taskkill nao pode ser chamado para entrada bloqueada")
    monkeypatch.setattr(processes.subprocess, "run", forbidden)
    _result(
        processes.encerrar_processo_windows(**args),
        ok=False, code=code, tool="encerrar_processo_windows",
    )


def test_process_identity_unavailable_is_failure_not_success(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: "")
    _result(
        processes.encerrar_processo_windows(pid=234),
        ok=False, code="process_identity_unverified", tool="encerrar_processo_windows",
    )


def test_protected_process_by_pid_cannot_be_terminated(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: "explorer.exe")
    _result(
        processes.encerrar_processo_windows(pid=234),
        ok=False, code="protected_process_blocked", tool="encerrar_processo_windows",
    )


def test_taskkill_unknown_failure_message_stays_failure_and_countable(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: "steam.exe")
    monkeypatch.setattr(
        processes.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=128, stdout="", stderr="Zugriff verweigert"),
    )
    value = processes.encerrar_processo_windows(pid=123, nome="steam.exe")
    _result(value, ok=False, code="process_termination_command_failed", tool="encerrar_processo_windows")
    assert "Zugriff verweigert" in value.message


def test_taskkill_exception_stays_failure_even_when_text_is_unrecognized(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: "steam.exe")
    def explode(*a, **kw):
        raise RuntimeError("WERT_FREMDE_MELDUNG")
    monkeypatch.setattr(processes.subprocess, "run", explode)
    value = processes.encerrar_processo_windows(pid=123, nome="steam.exe")
    _result(value, ok=False, code="process_termination_exception", tool="encerrar_processo_windows")
    assert "WERT_FREMDE_MELDUNG" in value.message


def test_taskkill_success_only_acks_request_and_not_process_exit(monkeypatch):
    _windows(monkeypatch)
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: "steam.exe")
    commands = []
    def fake_run(cmd, **kw):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout="SUCCESS", stderr="")
    monkeypatch.setattr(processes.subprocess, "run", fake_run)
    result = processes.encerrar_processo_windows(pid=123, nome="steam.exe")
    _result(result, ok=True, code=None, tool="encerrar_processo_windows")
    assert result.data["solicitacao_enviada"] is True
    assert result.data["encerramento_comprovado"] is False
    assert commands == [["taskkill", "/PID", "123"]]


def test_all_windows_process_entrypoints_return_structured_results():
    # Barreiras minimas de contrato: nenhum return de mensagem solta em caminhos
    # desses executores. Leitores de PID privados nao entram na regra.
    from inspect import getsource
    for function in (
        processes.listar_processos_windows,
        processes.encerrar_processo_windows,
    ):
        source = getsource(function)
        import ast
        tree = ast.parse(source)
        returns = [node for node in ast.walk(tree) if isinstance(node, ast.Return)]
        assert returns, function.__name__
        for statement in returns:
            assert isinstance(statement.value, ast.Call)
            assert isinstance(statement.value.func, ast.Attribute)
            assert isinstance(statement.value.func.value, ast.Name)
            assert statement.value.func.value.id == "ToolResult"
            assert statement.value.func.attr in {"success", "failure"}
