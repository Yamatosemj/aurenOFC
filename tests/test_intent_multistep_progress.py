"""Regressao: revisor nao deve confundir passo valido com conclusao total.

Os resultados de IA, Windows e processos sao simulados. Nenhuma acao real
ou API paga e executada por estes testes.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from core.harness import AurenHarness
from core.harness_intent_guard import verificar_antes_de_agir
from core.intent_verification import (
    INSTRUCTIONS, IntentDecision, criar_entrada_verificacao, proposta_simples_exata,
)
from core.task_manager import TaskState


def _call(nome, argumentos):
    return SimpleNamespace(
        type="function_call",
        name=nome,
        arguments=json.dumps(argumentos),
        call_id=f"call-{nome}",
    )


def _response(*calls, texto=""):
    return SimpleNamespace(output=list(calls), output_text=texto, usage=None)


def test_instrucoes_separam_progresso_de_resultado_e_preservam_permissoes():
    assert "PROXIMO PASSO" in INSTRUCTIONS
    assert "pode ser APROVADA mesmo que" in INSTRUCTIONS
    assert "sozinha nao conclua a tarefa" in INSTRUCTIONS
    assert "nao BLOQUEIE apenas" in INSTRUCTIONS
    assert "explorer.exe" in INSTRUCTIONS
    assert "PID" in INSTRUCTIONS
    assert "PermissionManager" in INSTRUCTIONS


def test_proposta_de_pid_principal_com_evidencia_passou_a_fast_review_local():
    proposta = _call("encerrar_processo_windows", {"pid": 19380, "nome": ""})
    historico = [
        {
            "ferramenta": "listar_janelas_windows",
            "resultado": "Nenhuma janela Steam visivel",
            "argumentos": "{}",
        },
        {
            "ferramenta": "listar_processos_windows",
            "resultado": (
                "Processos encontrados: 3\n"
                "steam.exe | PID 19380 | memoria 87000 K\n"
                "steamservice.exe | PID 10760 | memoria 13000 K\n"
                "steamwebhelper.exe | PID 8636 | memoria 16000 K"
            ),
            "argumentos": '{"filtro":"steam"}',
        },
    ]
    payload = json.loads(
        criar_entrada_verificacao("feche a Steam por completo", [proposta], historico)
    )
    assert payload["pedido_original"] == "feche a Steam por completo"
    assert json.loads(payload["acoes_propostas"][0]["argumentos"])["pid"] == 19380
    assert "steamservice.exe" in payload["passos_anteriores_como_dados"][-1]["resultado"]
    # Somente o processo principal com PID presente na listagem atual entra
    # na revisao deterministica; a permissao de encerrar continua CONFIRM.
    assert proposta_simples_exata("feche a Steam por completo", [proposta], historico) is True


def test_passo_parcial_aprovado_ainda_requer_consulta_para_concluir():
    recebidas = [
        _response(_call("listar_processos_windows", {"filtro": "steam"})),
        _response(_call("encerrar_processo_windows", {"pid": 19380, "nome": ""})),
        _response(texto="Steam encerrada por completo."),
        _response(_call("listar_processos_windows", {"filtro": "steam"})),
        _response(texto="Nao ha mais processos relacionados a Steam."),
    ]
    ferramentas = []
    revisoes = []
    chamadas_modelo = []

    def modelo(entrada, *args):
        chamadas_modelo.append((entrada, args))
        return recebidas.pop(0)

    def ferramenta(item):
        ferramentas.append(item.name)
        if item.name == "listar_processos_windows":
            if ferramentas.count("listar_processos_windows") == 1:
                return (
                    "Processos encontrados: 2\n"
                    "steam.exe | PID 19380 | memoria 87000 K\n"
                    "steamwebhelper.exe | PID 8636 | memoria 16000 K"
                )
            return "Nenhum processo corresponde a 'steam'."
        if item.name == "encerrar_processo_windows":
            return "Processo encerrado."
        raise AssertionError("ferramenta inesperada")

    def revisor(objetivo, calls, historico):
        revisoes.append((objetivo, calls[0].name, list(historico)))
        return IntentDecision("aprovar", "PID observado; passo parcial do objetivo")

    harness = AurenHarness(
        criar_resposta=modelo,
        executar_ferramenta=ferramenta,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda resp: [i for i in resp.output if i.type == "function_call"],
        comando_rapido=lambda _: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=revisor,
    )
    _, resposta = harness.processar_mensagem("feche a Steam por completo")
    assert harness.current_task().state is TaskState.COMPLETED
    assert resposta.output_text == "Nao ha mais processos relacionados a Steam."
    assert ferramentas == [
        "listar_processos_windows",
        "encerrar_processo_windows",
        "listar_processos_windows",
    ]
    # Preflight estrito com PID e nome observados substitui somente a segunda
    # revisao por IA; o proprio teste comprova a verificacao depois da acao.
    assert len(revisoes) == 0
    assert len(chamadas_modelo) == 5  # reconsulta obrigatoria apos acao mutante


def test_revisor_que_bloqueia_alvo_errado_ainda_interrompe_execucao():
    eventos = []
    proposta = [_call("encerrar_processo_windows", {"pid": 1234, "nome": "explorer.exe"})]
    executados = []
    harness = SimpleNamespace(
        _task_id="teste-bloqueio",
        verificar_intencao=lambda *_: IntentDecision(
            "bloquear", "explorer.exe nao faz parte do pedido Steam"
        ),
        task_manager=SimpleNamespace(should_cancel=lambda *_: False),
        _encerrar_falha=lambda codigo, mensagem, rodada: (False, codigo),
        executar_ferramenta=lambda call: executados.append(call),
    )
    result = verificar_antes_de_agir(
        harness, "feche a Steam por completo", proposta, [],
        rodada=1, resposta_wrapper=lambda x: x,
        write_log=lambda evento, **dados: eventos.append((evento, dados)),
    )
    assert result == (False, "intent_verification_blocked")
    assert executados == []
    assert any(evento == "INTENT_VERIFICATION_RESULT" and dados["decisao"] == "bloquear"
               for evento, dados in eventos)
