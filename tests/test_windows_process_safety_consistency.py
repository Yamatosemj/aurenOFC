"""Protecoes de encerramento de processos em /IM, /PID e /F.

Todos os testes usam Windows simulado, identidade falsa de PIDs e subprocess
interceptado. Nunca executam taskkill, tools reais, API ou Windows pessoal.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_result import ToolResult
from tools import windows_processes as processes
from tools.windows_process_policy import (
    PROTECTED_PROCESS_NAMES,
    is_inside_windows_directory,
    is_protected_process_name,
)


@pytest.fixture
def fake_windows(monkeypatch):
    commands = []
    identities = {19380: "steam.exe", 101: "svchost.exe", 102: "taskhostw.exe"}
    paths = {19380: r"C:\Program Files\Steam\steam.exe"}
    monkeypatch.setattr(
        processes, "os",
        SimpleNamespace(name="nt", getpid=lambda: 9999, environ={"SystemRoot": r"C:\Windows"}),
    )
    monkeypatch.setattr(processes, "_nome_executavel_por_pid_windows", lambda pid: identities.get(pid, ""))
    monkeypatch.setattr(processes, "_caminho_executavel_por_pid_windows", lambda pid: paths.get(pid, ""))
    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="Solicitacao enviada", stderr="")
    monkeypatch.setattr(processes.subprocess, "run", fake_run)
    return commands, identities, paths


@pytest.mark.parametrize("name", sorted(PROTECTED_PROCESS_NAMES))
def test_all_protected_process_names_are_rejected_by_image_before_taskkill(fake_windows, name):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(nome=name.upper())
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error_code == "protected_process_blocked"
    assert commands == []
    assert is_protected_process_name(name.upper())


@pytest.mark.parametrize("name", [
    "svchost.exe", "taskhostw.exe", "fontdrvhost.exe", "sihost.exe",
    "registry", "memcompression", "explorer.exe",
])
def test_pid_normal_mode_blocks_protected_processes_without_taskkill(fake_windows, name):
    commands, identities, _ = fake_windows
    identities[110] = name
    result = processes.encerrar_processo_windows(pid=110)
    assert result.ok is False
    assert result.error_code == "protected_process_blocked"
    assert commands == []


def test_name_cannot_disguise_verified_pid_normal_mode(fake_windows):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(pid=19380, nome="chrome.exe")
    assert not result.ok
    assert result.error_code == "process_identity_mismatch"
    assert commands == []


@pytest.mark.parametrize("pid", [True, False])
def test_boolean_pid_does_not_coerce_into_process_identifier(fake_windows, pid):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(pid=pid, nome="steam.exe")
    assert not result.ok
    assert result.error_code == "pid_invalid"
    assert commands == []


def test_name_mode_still_sends_non_forced_request_for_safe_app(fake_windows):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(nome="steam.exe")
    assert result.ok
    assert result.data["encerramento_comprovado"] is False
    assert commands == [["taskkill", "/IM", "steam.exe"]]


def test_pid_normal_mode_with_exact_name_keeps_existing_contract(fake_windows):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(pid=19380, nome="steam.exe")
    assert result.ok
    assert commands == [["taskkill", "/PID", "19380"]]
    assert result.data["encerramento_comprovado"] is False


def test_pid_normal_mode_without_name_keeps_legacy_contract(fake_windows):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(pid=19380)
    assert result.ok
    assert commands == [["taskkill", "/PID", "19380"]]


def test_forced_mode_still_requires_exact_identity_and_uses_f(fake_windows):
    commands, _, _ = fake_windows
    result = processes.encerrar_processo_windows(pid=19380, nome="steam.exe", forcar=True)
    assert result.ok
    assert commands == [["taskkill", "/F", "/PID", "19380"]]
    assert result.data["encerramento_comprovado"] is False


def test_forced_mode_rejects_windows_directory_even_nonlisted_name(fake_windows):
    commands, _, paths = fake_windows
    paths[19380] = r"C:\Windows\System32\otherapp.exe"
    result = processes.encerrar_processo_windows(pid=19380, nome="otherapp.exe", forcar=True)
    assert not result.ok
    assert result.error_code == "force_windows_process_blocked"
    assert commands == []


def test_windows_path_protection_respects_component_boundary():
    assert is_inside_windows_directory(
        r"C:\Windows\System32\app.exe", r"C:\Windows"
    )
    assert not is_inside_windows_directory(
        r"C:\WindowsBackup\app.exe", r"C:\Windows"
    )
    assert not is_inside_windows_directory(
        r"D:\Windows\app.exe", r"C:\Windows"
    )


@pytest.mark.parametrize("forcar", [False, True])
def test_every_process_termination_still_needs_explicit_permission(forcar):
    level, reason = PermissionManager().nivel_da_acao(
        "encerrar_processo_windows",
        {"pid": 19380, "nome": "steam.exe", "forcar": forcar},
    )
    assert level is PermissionLevel.CONFIRM
    if forcar:
        assert "FORCADO" in reason


def test_policy_is_a_single_protected_name_source_not_patched_per_mode():
    import inspect
    src = inspect.getsource(processes.encerrar_processo_windows)
    assert "is_protected_process_name(nome_real)" in src
    assert "is_protected_process_name(alvo)" in src
    assert "protegidos = " not in src
