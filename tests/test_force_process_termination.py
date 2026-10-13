"""Encerramento forcado: testes sinteticos, sem executar taskkill real."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.intent_verification import passo_principal_de_encerramento_comprovado
from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_contracts import validate_tool_arguments
from core.tools_registry import tools
from core.tool_result import ToolResult
from tools import windows_processes


def _ambiente_windows_simulado(monkeypatch, caminho=r"C:\Program Files (x86)\Steam\steam.exe"):
    monkeypatch.setattr(
        windows_processes, "os",
        SimpleNamespace(
            name="nt",
            getpid=lambda: 999,
            environ={"SystemRoot": r"C:\Windows"},
        ),
    )
    monkeypatch.setattr(
        windows_processes, "_caminho_executavel_por_pid_windows",
        lambda _pid: caminho,
    )
    chamadas = []

    def fake_run(cmd, **_kwargs):
        chamadas.append(cmd)
        return SimpleNamespace(returncode=0, stdout="SUCCESS: signal sent", stderr="")

    monkeypatch.setattr(windows_processes.subprocess, "run", fake_run)
    return chamadas


def test_schema_force_strict_sem_adicionar_ferramenta():
    schema = next(x["parameters"] for x in tools if x["name"] == "encerrar_processo_windows")
    assert {"pid", "nome", "forcar"} == set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["forcar"]["type"] == "boolean"
    ok, _ = validate_tool_arguments(
        "encerrar_processo_windows", {"pid": 19380, "nome": "steam.exe", "forcar": True}
    )
    assert ok
    ok, _ = validate_tool_arguments(
        "encerrar_processo_windows", {"pid": 19380, "nome": "steam.exe", "forcar": "true"}
    )
    assert not ok


def test_forcar_exige_confirmacao_com_aviso_especifico():
    nivel, motivo = PermissionManager().nivel_da_acao(
        "encerrar_processo_windows",
        {"pid": 19380, "nome": "steam.exe", "forcar": True},
    )
    assert nivel is PermissionLevel.CONFIRM
    assert "FORCADO" in motivo


@pytest.mark.parametrize("pid,nome", [(None, "steam.exe"), (0, "steam.exe"), (19380, "")])
def test_nao_forca_sem_pid_e_nome(monkeypatch, pid, nome):
    comandos = _ambiente_windows_simulado(monkeypatch)
    resultado = windows_processes.encerrar_processo_windows(pid=pid, nome=nome, forcar=True)
    assert isinstance(resultado, ToolResult)
    assert not resultado.ok
    assert comandos == []


def test_nao_forca_nome_diferente_da_imagem_real(monkeypatch):
    comandos = _ambiente_windows_simulado(monkeypatch)
    resultado = windows_processes.encerrar_processo_windows(
        pid=19380, nome="chrome.exe", forcar=True
    )
    assert not resultado.ok
    assert resultado.error_code == "force_identity_mismatch"
    assert comandos == []


def test_nao_forca_imagem_sem_identidade(monkeypatch):
    comandos = _ambiente_windows_simulado(monkeypatch, caminho="")
    resultado = windows_processes.encerrar_processo_windows(
        pid=19380, nome="steam.exe", forcar=True
    )
    assert not resultado.ok
    assert resultado.error_code == "force_identity_unverified"
    assert comandos == []


def test_nao_forca_processos_da_pasta_windows(monkeypatch):
    comandos = _ambiente_windows_simulado(monkeypatch, caminho=r"C:\Windows\System32\svchost.exe")
    resultado = windows_processes.encerrar_processo_windows(
        pid=1512, nome="svchost.exe", forcar=True
    )
    assert not resultado.ok
    assert comandos == []


def test_forca_pid_verificado_mas_nao_declara_conclusao(monkeypatch):
    comandos = _ambiente_windows_simulado(monkeypatch)
    resultado = windows_processes.encerrar_processo_windows(
        pid=19380, nome="steam.exe", forcar=True
    )
    assert isinstance(resultado, ToolResult)
    assert resultado.ok
    assert resultado.data["forcado"] is True
    assert resultado.data["encerramento_comprovado"] is False
    assert "verificado em nova listagem" in resultado.message
    assert comandos == [["taskkill", "/F", "/PID", "19380"]]


def test_modo_normal_conserva_taskkill_sem_f(monkeypatch):
    comandos = _ambiente_windows_simulado(monkeypatch)
    monkeypatch.setattr(
        windows_processes, "_nome_executavel_por_pid_windows",
        lambda _pid: "steam.exe",
    )
    resultado = windows_processes.encerrar_processo_windows(pid=19380, nome="steam.exe")
    assert resultado.ok
    assert resultado.data["forcado"] is False
    assert comandos == [["taskkill", "/PID", "19380"]]


def test_forca_nunca_pula_revisor_semantico():
    from types import SimpleNamespace
    historico = [{
        "ferramenta": "listar_processos_windows",
        "argumentos": '{"filtro":"steam"}',
        "resultado": "Processos encontrados: 1\\nsteam.exe | PID 19380 | memoria 20 K",
    }]
    normal = [SimpleNamespace(
        name="encerrar_processo_windows",
        arguments='{"pid":19380,"nome":"steam.exe","forcar":false}',
    )]
    forcado = [SimpleNamespace(
        name="encerrar_processo_windows",
        arguments='{"pid":19380,"nome":"steam.exe","forcar":true}',
    )]
    assert passo_principal_de_encerramento_comprovado(
        "feche Steam por completo", normal, historico
    )
    assert not passo_principal_de_encerramento_comprovado(
        "feche Steam por completo", forcado, historico
    )
