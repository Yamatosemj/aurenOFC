"""Falha real: taskkill aceito, PID Steam intacto, tentativas repetidas.

Tudo offline: callbacks simulam ferramentas; nenhum processo e encerrado,
nenhum pedido e enviado ao provedor e nenhum dialogo e aberto no Windows.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.harness_closure import (
    _encerramento_sem_progresso,
    _repeticao_encerramento_sem_verificar,
)
from core.task_manager import TaskState
from core.tool_result import ToolResult
from tools import windows_processes


LISTA_STEAM = (
    "Processos encontrados: 3\n"
    "steam.exe | PID 19380 | memoria 91180 K\n"
    "steamservice.exe | PID 10760 | memoria 13452 K\n"
    "steamwebhelper.exe | PID 8636 | memoria 158012 K"
)
LISTA_SEM_PRINCIPAL = (
    "Processos encontrados: 2\n"
    "steamservice.exe | PID 10760 | memoria 13452 K\n"
    "steamwebhelper.exe | PID 8636 | memoria 158012 K"
)


def _call(nome, args=None):
    return SimpleNamespace(
        type="function_call", name=nome,
        arguments=json.dumps(args or {}), call_id="test-" + nome,
    )


def _resp(*calls, texto=""):
    return SimpleNamespace(output=list(calls), output_text=texto, usage=None)


def _historico(antes=LISTA_STEAM, depois=LISTA_STEAM, mutante=None):
    return [
        {"ferramenta": "listar_processos_windows",
         "argumentos": '{"filtro":"steam"}', "resultado": antes},
        {"ferramenta": "encerrar_processo_windows",
         "argumentos": json.dumps(mutante or {"pid":19380, "nome":""}),
         "resultado": "Pedido de encerramento enviado"},
        {"ferramenta": "listar_processos_windows",
         "argumentos": '{"filtro":"steam"}', "resultado": depois},
    ]


def test_steam_pid_inalterado_depois_de_taskkill_e_sem_progresso():
    assert _encerramento_sem_progresso(
        "Auren, feche a Steam por completo", _historico()
    ) == {"pid": 19380, "processo": "steam.exe"}


def test_main_pid_desapareceu_permite_continuar_com_helpers():
    assert _encerramento_sem_progresso(
        "feche Steam por completo", _historico(depois=LISTA_SEM_PRINCIPAL)
    ) is None


def test_nao_falsifica_sem_progresso_em_comando_de_janela_ou_leitura_antiga():
    assert _encerramento_sem_progresso("feche a Steam", _historico()) is None
    assert _encerramento_sem_progresso(
        "feche Steam por completo", _historico()[:-1]
    ) is None
    antigo = _historico()
    antigo[-1]["argumentos"] = '{"filtro":"chrome"}'
    assert _encerramento_sem_progresso("feche Steam por completo", antigo) is None


@pytest.mark.parametrize("resultado_falha", [
    json.dumps({
        "ok": False,
        "mensagem": "ACAO NAO EXECUTADA: Usuario negou a acao.",
        "codigo_erro": "permission_denied",
    }),
    json.dumps({
        "ok": False,
        "mensagem": "Nao consegui solicitar o encerramento.",
        "codigo_erro": "process_termination_command_failed",
    }),
    "Nao consegui encerrar o processo: acesso negado",
])
def test_pid_ativo_apos_acao_negada_ou_falha_nao_finge_sinal_enviado(resultado_falha):
    historico = _historico()
    historico[1]["resultado"] = resultado_falha
    assert _encerramento_sem_progresso(
        "feche Steam por completo", historico,
    ) is None


def test_nome_em_vez_de_pid_que_permanece_tambem_e_detectado():
    assert _encerramento_sem_progresso(
        "feche steam por completo",
        _historico(mutante={"pid":0,"nome":"steam.exe"})
    ) == {"pid":19380, "processo":"steam.exe"}


def test_modelo_nao_pode_reenviar_pid_sem_nova_consulta():
    hist = _historico()[:-1]
    assert _repeticao_encerramento_sem_verificar(
        "feche a Steam por completo",
        [_call("encerrar_processo_windows", {"pid":19380,"nome":""})], hist
    )
    assert not _repeticao_encerramento_sem_verificar(
        "feche a Steam por completo",
        [_call("encerrar_processo_windows", {"pid":10760,"nome":""})], hist
    )
    assert not _repeticao_encerramento_sem_verificar(
        "feche a Steam por completo",
        [_call("listar_processos_windows", {"filtro":"steam"})], hist
    )


def _harness(respostas, tool_function):
    calls = []
    requested = []
    queue = list(respostas)

    def modelo(entrada, *_args):
        requested.append(entrada)
        return queue.pop(0)

    def executar(call):
        calls.append(call.name)
        return tool_function(call)

    h = AurenHarness(
        criar_resposta=modelo,
        executar_ferramenta=executar,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda r: [v for v in r.output if v.type == "function_call"],
        comando_rapido=lambda _: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=None,
    )
    return h, calls, requested


def test_reproducao_real_falha_apos_primeira_reconsulta_sem_chamadas_extra():
    def ferramenta(call):
        if call.name == "listar_processos_windows":
            return LISTA_STEAM
        if call.name == "encerrar_processo_windows":
            return ToolResult.success(
                "Pedido enviado, encerramento nao confirmado",
                data={"encerramento_comprovado": False},
            )
        raise AssertionError(call.name)

    h, calls, modelos = _harness([
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(_call("encerrar_processo_windows", {"pid":19380,"nome":""})),
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        # Se a protecao falhar, o teste aborta ao tentar obter outro modelo.
    ], ferramenta)
    _, resposta = h.processar_mensagem("feche a Steam por completo")
    assert h.current_task().state is TaskState.FAILED
    assert "continua ativo" in resposta.output_text
    assert "nao foi concluida" in resposta.output_text
    assert calls == [
        "listar_processos_windows", "encerrar_processo_windows", "listar_processos_windows"
    ]
    assert len(modelos) == 3


def test_repeticao_imediata_sem_consulta_interrompe_antes_da_segunda_execucao():
    def ferramenta(call):
        if call.name == "listar_processos_windows":
            return LISTA_STEAM
        if call.name == "encerrar_processo_windows":
            return "Pedido enviado"
        raise AssertionError(call.name)

    h, calls, _modelos = _harness([
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(_call("encerrar_processo_windows", {"pid":19380,"nome":""})),
        _resp(_call("encerrar_processo_windows", {"pid":19380,"nome":""})),
    ], ferramenta)
    _, resposta = h.processar_mensagem("feche a Steam por completo")
    assert h.current_task().state is TaskState.FAILED
    assert "Interrompi a repeticao" in resposta.output_text
    assert calls.count("encerrar_processo_windows") == 1


def test_taskkill_sucesso_so_confirma_envio_nao_encerramento(monkeypatch):
    fake_os = SimpleNamespace(name="nt", getpid=lambda: 9999)
    monkeypatch.setattr(windows_processes, "os", fake_os)
    monkeypatch.setattr(
        windows_processes,
        "_nome_executavel_por_pid_windows",
        lambda pid: "steam.exe",
    )
    comandos = []
    def fake_run(cmd, **kwargs):
        comandos.append(cmd)
        return SimpleNamespace(returncode=0, stdout="SUCCESS: signal sent", stderr="")
    monkeypatch.setattr(windows_processes.subprocess, "run", fake_run)
    resultado = windows_processes.encerrar_processo_windows(pid=19380, nome="")
    assert isinstance(resultado, ToolResult)
    assert resultado.ok
    assert resultado.data["encerramento_comprovado"] is False
    assert "nao declare" in resultado.message
    assert comandos == [["taskkill", "/PID", "19380"]]


def test_taskkill_erro_usa_toolresult_failure(monkeypatch):
    monkeypatch.setattr(
        windows_processes, "os", SimpleNamespace(name="nt", getpid=lambda: 9999)
    )
    monkeypatch.setattr(
        windows_processes, "_nome_executavel_por_pid_windows",
        lambda pid: "steam.exe",
    )
    monkeypatch.setattr(
        windows_processes.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="Access is denied"),
    )
    resultado = windows_processes.encerrar_processo_windows(pid=19380)
    assert isinstance(resultado, ToolResult)
    assert not resultado.ok
    assert resultado.error_code == "process_termination_command_failed"
