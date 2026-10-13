"""Regressoes de 'sim auren' e revisao de PID principal comprovado.

Somente mocks; nao encerra processos no Windows e nao chama a API.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.harness_followup import PerguntaPendente, resolver_continuacao
from core.intent_verification import (
    criar_entrada_verificacao,
    passo_principal_de_encerramento_comprovado,
    proposta_simples_exata,
)
from core.permission_manager import PermissionLevel, PermissionManager
from core.task_manager import TaskState


def _call(nome, argumentos):
    return SimpleNamespace(
        type="function_call", name=nome,
        arguments=json.dumps(argumentos), call_id="call-"+nome,
    )


def _response(*calls, texto=""):
    return SimpleNamespace(output=list(calls), output_text=texto, usage=None)


@pytest.mark.parametrize("resposta", ["sim", "SIM", "sim auren", "Sim, Auren!", "pode sim auren"])
def test_reconhece_sim_para_pergunta_pendente_sem_anexar_novo_objetivo(resposta):
    pendente = PerguntaPendente(
        "auren, feche steam por completo",
        "Você quer encerrar todos os processos relacionados ao Steam?",
    )
    objetivo, estado = resolver_continuacao(pendente, resposta)
    assert estado == "normal"
    assert objetivo == "auren, feche steam por completo"
    assert "Pergunta pendente" not in objetivo


def test_resposta_isolada_ou_negativa_nao_reexecuta_tarefa():
    assert resolver_continuacao(None, "sim auren") == ("sim auren", "sem_pendencia")
    assert resolver_continuacao(
        PerguntaPendente("feche a Steam", "Posso fechar?"), "nao"
    ) == ("feche a Steam", "cancelar")


def test_confirmacao_verdadeira_e_campo_separado_de_tools():
    marcador = {"ferramenta": "__confirmacao_usuario_pendente__", "resultado": "Encerrar todos os processos Steam?"}
    historico = [
        {"ferramenta": "listar_processos_windows",
         "argumentos": '{"filtro":"steam"}',
         "resultado": "Processos encontrados: 1\\nsteam.exe | PID 19380 | memoria 123"},
        marcador,
    ]
    dados = json.loads(criar_entrada_verificacao(
        "feche a Steam por completo",
        [_call("encerrar_processo_windows", {"pid": 19380})],
        historico,
    ))
    assert dados["confirmacao_usuario_ao_esclarecimento"] == {
        "pergunta": "Encerrar todos os processos Steam?", "resposta": "sim"
    }
    assert len(dados["passos_anteriores_como_dados"]) == 1
    assert dados["passos_anteriores_como_dados"][0]["ferramenta"] == "listar_processos_windows"


def _historico(pid=19380, nome="steam.exe", filtro="steam"):
    return [{
        "ferramenta": "listar_processos_windows",
        "argumentos": json.dumps({"filtro": filtro}),
        "resultado": (
            f"Processos encontrados: 2\n{nome} | PID {pid} | memoria 100 K"
            "\nsteamwebhelper.exe | PID 8636 | memoria 200 K"
        ),
    }]


def test_passo_principal_pid_comprovado_aceito_sem_segunda_ia():
    acao = [_call("encerrar_processo_windows", {"pid": 19380})]
    assert passo_principal_de_encerramento_comprovado(
        "feche Steam por completo", acao, _historico(),
    )
    assert proposta_simples_exata("feche Steam por completo", acao, _historico())


@pytest.mark.parametrize("nome,pid,filtro,objetivo", [
    ("explorer.exe", 19380, "steam", "feche Steam por completo"),
    ("steamwebhelper.exe", 19380, "steam", "feche Steam por completo"),
    ("steam.exe", 19381, "steam", "feche Steam por completo"),
    ("steam.exe", 19380, "chrome", "feche Steam por completo"),
    ("steam.exe", 19380, "steam", "feche Steam"),
    ("steam.exe", 19380, "steam", "abra Steam"),
    ("steam.exe", 19380, "steam", "feche Steam por completo e apague arquivos"),
])
def test_sem_prova_exata_nao_salta_revisor(nome,pid,filtro,objetivo):
    acao = [_call("encerrar_processo_windows", {"pid": 19380})]
    assert not passo_principal_de_encerramento_comprovado(
        objetivo, acao, _historico(pid=pid, nome=nome, filtro=filtro)
    )
    assert not proposta_simples_exata(
        objetivo, acao, _historico(pid=pid, nome=nome, filtro=filtro)
    )


@pytest.mark.parametrize("args", [
    {"pid": "19380"}, {"pid": 19380, "nome": "explorer.exe"},
    {"pid": 19380, "extra": "erro"}, {"pid": True},
])
def test_argumento_do_processo_ambiguo_continua_no_revisor(args):
    assert not passo_principal_de_encerramento_comprovado(
        "feche Steam por completo", [_call("encerrar_processo_windows", args)], _historico()
    )


def test_ferramenta_principal_continua_exigindo_confirmacao():
    manager = PermissionManager()
    nivel, _ = manager.nivel_da_acao("encerrar_processo_windows", {"pid": 19380})
    assert nivel == PermissionLevel.CONFIRM


def test_revisor_nao_repete_pergunta_ja_respondida():
    chamadas_modelo = []
    sentencas = []
    respostas = [
        _response(_call("listar_processos_windows", {"filtro": "steam"})),
        # Primeiro o modelo propoe helper: revisao por IA (nao fast path).
        _response(_call("encerrar_processo_windows", {"pid": 8636})),
        _response(_call("listar_processos_windows", {"filtro": "steam"})),
        _response(_call("encerrar_processo_windows", {"pid": 19380})),
        _response(texto="Steam encerrada"),
        _response(_call("listar_processos_windows", {"filtro": "steam"})),
        _response(texto="Steam encerrada e verificada"),
    ]

    def modelo(inp, *_args):
        chamadas_modelo.append(inp)
        return respostas.pop(0)

    def ferramenta(item):
        sentencas.append(item.name)
        if item.name == "listar_processos_windows" and sentencas.count("listar_processos_windows") >= 3:
            return "Nenhum processo corresponde a 'steam'."
        if item.name == "listar_processos_windows":
            return ("Processos encontrados: 2\nsteam.exe | PID 19380 | memoria 100 K"
                    "\nsteamwebhelper.exe | PID 8636 | memoria 100 K")
        if item.name == "encerrar_processo_windows":
            return "Processo encerrado."
        raise AssertionError(item.name)

    revisoes = []
    def revisor(objetivo, calls, historico):
        revisoes.append(criar_entrada_verificacao(objetivo, calls, historico))
        return SimpleNamespace(
            decisao="esclarecer", motivo="confirmar escopo",
            pergunta="Você quer encerrar todos os processos relacionados ao Steam?",
        )

    harness = AurenHarness(
        criar_resposta=modelo, executar_ferramenta=ferramenta,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [x for x in response.output if x.type=="function_call"],
        comando_rapido=lambda _: (False, ""),
        iniciar_tarefa=lambda: None, apos_tarefa=None, fechar=lambda: None,
        verificar_intencao=revisor,
    )
    _, pergunta = harness.processar_mensagem("feche steam por completo")
    assert pergunta.output_text.endswith("?")
    assert len(revisoes) == 1

    # Depois do SIM o processo principal comprovado e validado por regra
    # deterministica e vai para o executor/PermissionManager normal.
    _, resposta = harness.processar_mensagem("sim auren")
    assert sentencas == [
        "listar_processos_windows",
        "listar_processos_windows",
        "encerrar_processo_windows",
        "listar_processos_windows",
    ]
    assert resposta.output_text == "Steam encerrada e verificada"
    assert len(revisoes) == 1
    assert harness.current_task().objective == "feche steam por completo"
    assert "Pergunta pendente" not in harness.current_task().objective
    assert harness._confirmacao_esclarecimento is not None
