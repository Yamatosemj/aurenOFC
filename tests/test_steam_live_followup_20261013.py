"""Regressoes do teste Live de 13/10: SIM repetido e taskkill sem reconsulta.

Tudo usa modelo e ferramentas simulados; nenhum processo real e tocado.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.harness_closure import (
    _confirmacao_fechamento_ja_respondida,
    _reconsulta_processos_pendente,
)
from core.harness_followup import PerguntaPendente, resolver_continuacao
from core.intent_verification import IntentDecision
from core.task_manager import TaskState
from core.tool_result import ToolResult


PERGUNTA = "Confirma que devo forçar o fechamento de todos os processos da Steam?"
PERGUNTA_REPETIDA = (
    "Você confirma o encerramento forçado de todos os processos da Steam?"
)
PROCESSOS = (
    "Processos encontrados: 2\nsteam.exe | PID 19380 | memoria 100 K"
    "\nsteamservice.exe | PID 10760 | memoria 100 K"
)


def _call(nome, args=None):
    return SimpleNamespace(
        type="function_call", name=nome,
        arguments=json.dumps(args or {}), call_id="id-" + nome,
    )


def _resp(*calls, texto=""):
    return SimpleNamespace(output=list(calls), output_text=texto, usage=None)


def _harness(respostas, ferramenta, revisor=None):
    queue = list(respostas)
    inputs = []
    execucoes = []
    verificacoes = []

    def modelo(entrada, *args):
        inputs.append((entrada, args))
        return queue.pop(0)

    def executor(chamada):
        execucoes.append((chamada.name, json.loads(chamada.arguments)))
        return ferramenta(chamada)

    def revisar(objetivo, chamadas, historico):
        verificacoes.append((objetivo, [c.name for c in chamadas]))
        return revisor(objetivo, chamadas, historico) if revisor else IntentDecision("aprovar", "alvo correto")

    h = AurenHarness(
        criar_resposta=modelo,
        executar_ferramenta=executor,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda r: [v for v in r.output if v.type == "function_call"],
        comando_rapido=lambda _: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=revisar,
    )
    return h, inputs, execucoes, verificacoes


@pytest.mark.parametrize("resposta", [
    "sim", "SIM", "já disse que sim", "eu já disse que sim", "já confirmei"
])
def test_afirmacao_contextual_nunca_anexa_pergunta_ao_objetivo(resposta):
    pendente = PerguntaPendente("feche steam por completo", PERGUNTA)
    assert resolver_continuacao(pendente, resposta) == ("feche steam por completo", "normal")
    assert resolver_continuacao(None, resposta) == (resposta, "sem_pendencia")


def test_sim_respondido_nao_dispensa_permissao_semantica_ou_local():
    assert _confirmacao_fechamento_ja_respondida(
        "feche Steam por completo", PERGUNTA, PERGUNTA_REPETIDA
    )
    assert not _confirmacao_fechamento_ja_respondida(
        "feche Steam", PERGUNTA, PERGUNTA_REPETIDA
    )
    assert not _confirmacao_fechamento_ja_respondida(
        "feche Steam por completo", PERGUNTA,
        "Você autoriza fechar o Discord?"
    )
    assert not _confirmacao_fechamento_ja_respondida(
        "feche Steam por completo", PERGUNTA,
        "Qual PID está correto?"
    )


def test_pedido_de_reconsulta_so_para_estado_apos_taskkill():
    hist = [
        {"ferramenta":"listar_processos_windows",
         "argumentos":'{"filtro":"steam"}', "resultado":PROCESSOS},
        {"ferramenta":"encerrar_processo_windows",
         "argumentos":'{"pid":19380,"nome":"steam.exe","forcar":true}',
         "resultado":"Pedido de encerramento FORCADO enviado"},
    ]
    assert _reconsulta_processos_pendente("feche steam por completo", hist)
    assert not _reconsulta_processos_pendente("feche steam", hist)
    hist.append({"ferramenta":"listar_processos_windows",
                 "argumentos":'{"filtro":"steam.exe"}',
                 "resultado":"Nenhum processo corresponde a 'steam.exe'."})
    assert _reconsulta_processos_pendente("feche steam por completo", hist)
    hist.append({"ferramenta":"listar_processos_windows",
                 "argumentos":'{"filtro":"steam"}',
                 "resultado":"Nao consegui listar."})
    assert _reconsulta_processos_pendente("feche steam por completo", hist)
    hist.append({"ferramenta":"listar_processos_windows",
                 "argumentos":'{"filtro":"steam"}',
                 "resultado":"Nenhum processo corresponde a 'steam'."})
    assert not _reconsulta_processos_pendente("feche steam por completo", hist)


def test_live_regression_confirmacao_repetida_e_helper_prematuro():
    leituras = 0
    def ferramenta(chamada):
        nonlocal leituras
        if chamada.name == "listar_processos_windows":
            leituras += 1
            return PROCESSOS if leituras < 3 else "Nenhum processo corresponde a 'steam'."
        if chamada.name == "encerrar_processo_windows":
            assert json.loads(chamada.arguments)["pid"] == 19380
            return ToolResult.success(
                "Pedido de encerramento FORCADO enviado, ainda nao verificado.",
                data={"solicitacao_enviada":True, "encerramento_comprovado":False},
            )
        raise AssertionError(chamada.name)

    modelo = [
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(texto=PERGUNTA),
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(texto=PERGUNTA_REPETIDA),
        _resp(_call("encerrar_processo_windows", {
            "pid":19380,"nome":"steam.exe","forcar":True
        })),
        # Reproduz a tentativa indevida do log: helper sem nova consulta.
        _resp(_call("encerrar_processo_windows", {
            "pid":10760,"nome":"steamservice.exe","forcar":True
        })),
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(texto="Steam encerrada por completo e verificada."),
    ]
    h, inputs, executadas, revisoes = _harness(modelo, ferramenta)
    _, primeira = h.processar_mensagem("feche steam por completo")
    assert primeira.output_text == PERGUNTA

    _, segunda = h.processar_mensagem("sim")
    assert segunda.output_text == "Steam encerrada por completo e verificada."
    assert h.current_task().state is TaskState.COMPLETED
    assert h.current_task().objective == "feche steam por completo"
    assert [nome for nome, _ in executadas] == [
        "listar_processos_windows",
        "listar_processos_windows",
        "encerrar_processo_windows",
        "listar_processos_windows",
    ]
    assert any("guard_confirmacao_ja_respondida" in str(e[0]) for e in inputs)
    assert any("guard_processos_pos_acao" in str(e[0]) for e in inputs)
    assert any("ESCLARECIMENTO CONTEXTUAL JA RESPONDIDO" in str(e[0]) for e in inputs)
    assert all(obj == "feche steam por completo" for obj, _ in revisoes)


def test_repeticao_persistente_termina_sem_acao():
    def ferramenta(chamada):
        assert chamada.name == "listar_processos_windows"
        return PROCESSOS

    h, _inputs, feitas, _rev = _harness([
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(texto=PERGUNTA),
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(texto=PERGUNTA_REPETIDA),
        _resp(texto=PERGUNTA_REPETIDA),
    ], ferramenta)
    h.processar_mensagem("feche steam por completo")
    _, resposta = h.processar_mensagem("sim")
    assert "ja confirmou" in resposta.output_text
    assert h.current_task().state is TaskState.FAILED
    assert [f for f, _ in feitas] == ["listar_processos_windows"] * 2


def test_propostas_em_lote_com_taskkill_falham_antes_da_execucao():
    def ferramenta(chamada):
        assert chamada.name == "listar_processos_windows"
        return PROCESSOS

    h, _inputs, feitas, _rev = _harness([
        _resp(_call("listar_processos_windows", {"filtro":"steam"})),
        _resp(
            _call("encerrar_processo_windows", {"pid":19380,"nome":"steam.exe","forcar":True}),
            _call("encerrar_processo_windows", {"pid":10760,"nome":"steamservice.exe","forcar":True}),
        ),
    ], ferramenta)
    _, resposta = h.processar_mensagem("feche steam por completo")
    assert "lote" in resposta.output_text
    assert h.current_task().state is TaskState.FAILED
    assert [f for f, _ in feitas] == ["listar_processos_windows"]
