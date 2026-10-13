"""Regressoes do teste Live em 12/10/2026: feche Steam porcompleto.

Mocks: NAO chama Steam, Windows, API, Dispatcher nem um processo real.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from core.harness import AurenHarness
from core.harness_closure import _alvo_fechamento, _comprovou_fechamento
from core.harness_heuristics import _parece_tarefa_de_acao
from core.router import Router
from core.task_manager import TaskState
from core.tools_registry import tools


def _chamada(nome: str, args=None):
    return SimpleNamespace(
        name=nome, arguments=json.dumps(args or {}),
        call_id="call-" + nome, type="function_call",
    )


def _resposta(*calls, text=""):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


def _harness(respostas, ferramenta):
    chamadas = []
    pedidos = []
    restantes = list(respostas)

    def modelo(entrada, *args):
        pedidos.append((entrada, args))
        return restantes.pop(0)

    def executar(call):
        chamadas.append((call.name, json.loads(call.arguments)))
        return ferramenta(call)

    h = AurenHarness(
        criar_resposta=modelo,
        executar_ferramenta=executar,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda resp: [
            item for item in resp.output if item.type == "function_call"
        ],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )
    return h, chamadas, pedidos


def test_feche_e_imperativo_exigem_execucao_na_primeira_rodada():
    for pedido in (
        "feche a steam porcompleto",
        "feche a Steam",
        "auren, feche o Discord",
        "encerre a Steam",
        "termine o aplicativo",
    ):
        assert _parece_tarefa_de_acao(pedido), pedido


def test_router_fechamento_completo_disponibiliza_processos_e_janelas():
    router = Router()
    ferramentas = router.select_tool_names(
        "feche a steam porcompleto", tools,
    )
    assert {"listar_processos_windows", "encerrar_processo_windows",
            "fechar_janela_windows", "listar_janelas_windows"} <= set(ferramentas)
    assert "process" in router.last_domains
    assert "windows" in router.last_domains
    assert "navegar_navegador" not in ferramentas

    normal = Router().select_tool_names("feche a steam", tools)
    assert "fechar_janela_windows" in normal
    assert "encerrar_processo_windows" not in normal


def test_abrir_steam_nao_herda_rota_de_encerramento():
    nomes = Router().select_tool_names("abra a steam", tools)
    assert "abrir_programa" in nomes
    assert "encerrar_processo_windows" not in nomes


def test_nunca_valida_consulta_antiga_apos_fechar_a_janela():
    historico = [
        {"ferramenta": "listar_janelas_windows", "resultado": "Nenhuma janela visivel com titulo foi encontrada.", "argumentos": "{}"},
        {"ferramenta": "fechar_janela_windows", "resultado": "Solicitei o fechamento da janela: Steam", "argumentos": '{"alvo":"Steam"}'},
    ]
    assert not _comprovou_fechamento("feche a Steam", historico)
    assert not _comprovou_fechamento("feche a Steam porcompleto", historico)


def test_lista_de_janelas_nao_comprova_encerramento_completo():
    historico = [
        {"ferramenta": "fechar_janela_windows", "resultado": "Solicitei o fechamento da janela: Steam", "argumentos": '{"alvo":"Steam"}'},
        {"ferramenta": "listar_janelas_windows", "resultado": "Janelas visiveis: 1\n1. Chrome", "argumentos": "{}"},
    ]
    assert _comprovou_fechamento("feche a Steam", historico)
    assert not _comprovou_fechamento("feche a Steam porcompleto", historico)


def test_filtro_de_processo_incompleto_nao_comprova_encerramento_total():
    # Buscar apenas Steam.exe deixa SteamWebHelper fora do filtro.
    historico = [{
        "ferramenta": "listar_processos_windows",
        "resultado": "Nenhum processo corresponde a 'Steam.exe'.",
        "argumentos": '{"filtro":"Steam.exe"}',
    }]
    assert not _comprovou_fechamento("feche a Steam porcompleto", historico)


def test_harness_nao_encerra_apos_listar_janelas_e_verifica_depois_de_wm_close():
    quantidade = {"janelas": 0}

    def ferramenta(call):
        if call.name == "listar_janelas_windows":
            quantidade["janelas"] += 1
            return "Janelas visiveis: 2\n1. Steam\n2. Chrome" if quantidade["janelas"] == 1 else "Janelas visiveis: 1\n1. Chrome"
        if call.name == "fechar_janela_windows":
            return "Solicitei o fechamento da janela: Steam"
        raise AssertionError(call.name)

    h, chamadas, pedidos = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(_chamada("fechar_janela_windows", {"alvo": "Steam"})),
        _resposta(text="A Steam foi fechada."),
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(text="A janela da Steam foi fechada."),
    ], ferramenta)
    _, result = h.processar_mensagem("feche a Steam")

    assert h.current_task().state is TaskState.COMPLETED
    assert result.output_text == "A janela da Steam foi fechada."
    assert [nome for nome, _ in chamadas] == [
        "listar_janelas_windows", "fechar_janela_windows", "listar_janelas_windows"
    ]
    assert pedidos[0][1][-1] == "required"
    assert pedidos[3][1][-1] == "required"


def test_harness_fechamento_completo_requer_processos_ausentes():
    quant = {"processos": 0}
    def ferramenta(call):
        if call.name == "listar_janelas_windows":
            return "Janelas visiveis: 1\n1. Steam"
        if call.name == "fechar_janela_windows":
            return "Solicitei o fechamento da janela: Steam"
        if call.name == "listar_processos_windows":
            quant["processos"] += 1
            return (
                "Processos encontrados: 1\nSteamWebHelper.exe | PID 200 | memoria 10"
                if quant["processos"] == 1
                else "Nenhum processo corresponde a 'steam'."
            )
        if call.name == "encerrar_processo_windows":
            return "Processo encerrado."
        raise AssertionError(call.name)
    h, chamadas, _pedidos = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(_chamada("fechar_janela_windows", {"alvo": "Steam"})),
        _resposta(text="A Steam foi fechada."),
        _resposta(_chamada("listar_processos_windows", {"filtro": "steam"})),
        _resposta(_chamada("encerrar_processo_windows", {"nome": "steamwebhelper.exe", "pid": None})),
        _resposta(text="Tudo fechado."),
        _resposta(_chamada("listar_processos_windows", {"filtro": "steam"})),
        _resposta(text="A Steam foi encerrada por completo."),
    ], ferramenta)
    _, result = h.processar_mensagem("feche a steam porcompleto")
    assert result.output_text == "A Steam foi encerrada por completo."
    assert h.current_task().state is TaskState.COMPLETED
    assert [nome for nome, _ in chamadas][-3:] == [
        "listar_processos_windows", "encerrar_processo_windows", "listar_processos_windows"
    ]


def test_harness_falha_em_vez_de_inventar_fechamento_sem_evidencia():
    def ferramenta(call):
        assert call.name == "listar_janelas_windows"
        return "Janelas visiveis: 1\n1. Steam"

    h, chamadas, _pedidos = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(text="Fechou."),
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(text="Fechou."),
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(text="Fechou."),
    ], ferramenta)
    _, result = h.processar_mensagem("feche a Steam")
    assert "Nao consegui comprovar" in result.output_text
    assert h.current_task().state is TaskState.FAILED
    assert [name for name, _ in chamadas] == ["listar_janelas_windows"] * 3


def test_fechar_ja_fechado_pode_concluir_sem_acao_desnecessaria():
    assert _comprovou_fechamento("feche a Steam por completo", [{
        "ferramenta": "listar_processos_windows",
        "argumentos": '{"filtro":"steam"}',
        "resultado": "Nenhum processo corresponde a 'steam'.",
    }])
