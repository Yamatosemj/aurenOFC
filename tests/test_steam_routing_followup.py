"""Regressoes do incidente real: 'abra a Steam' -> pergunta -> 'sim'."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness import AurenHarness
from core.harness_heuristics import _pode_encerrar_localmente
from core.intent_verification import IntentDecision
from core.router import Router
from core.task_manager import TaskState


def _chamada(nome: str, args: str = "{}", call_id: str = "call") -> SimpleNamespace:
    return SimpleNamespace(type="function_call", name=nome, arguments=args, call_id=call_id)


def _resposta(*chamadas, texto: str = "") -> SimpleNamespace:
    return SimpleNamespace(output=list(chamadas), output_text=texto, usage=None)


def _harness(respostas, *, verificar=None):
    restantes = list(respostas)
    executadas = []
    objetivos_verificados = []
    chamadas_modelo = []

    def modelo(entrada, *_args):
        chamadas_modelo.append(entrada)
        return restantes.pop(0)

    def ferramenta(chamada):
        executadas.append((chamada.name, chamada.arguments))
        return "Steam iniciada" if chamada.name == "abrir_programa" else "Janelas: Chrome"

    def revisor(objetivo, chamadas, historico):
        objetivos_verificados.append(objetivo)
        return verificar(objetivo, chamadas, historico) if verificar else IntentDecision("aprovar", "acao corresponde")

    harness = AurenHarness(
        criar_resposta=modelo,
        executar_ferramenta=ferramenta,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda resp: [item for item in resp.output if item.type == "function_call"],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=revisor,
    )
    return harness, executadas, objetivos_verificados, chamadas_modelo


def test_router_ignora_instrucao_de_janelas_e_preserva_abrir_programa():
    router = Router()
    registry = [{"name": name} for name in (
        "listar_janelas_windows", "abrir_programa", "navegar_navegador",
        "obter_status_windows", "consultar_memoria_persistente",
    )]
    estado = (
        "CONTEXTO CONTROLADO DA TAREFA\n"
        "Objetivo original: auren, abra a steam\n"
        "TIPO: execucao controlada pelo harness\n"
        "Nunca reutilize coordenadas quando mover janelas ou o cursor.\n"
        "Historico: chrome, youtube, discord, volume, sistema."
    )
    for entrada in (
        estado,
        [{"role": "user", "content": [{"type": "input_text", "text": estado}]},
         {"type": "function_call_output", "call_id": "x", "output": "janelas discord"}],
    ):
        escolhidas = router.select_tool_names(entrada, registry)
        assert "abrir_programa" in escolhidas
        assert "listar_janelas_windows" in escolhidas
        assert "navegar_navegador" not in escolhidas
        assert router.last_domains == ["apps_files"]


def test_router_site_conhecido_nao_vira_aplicativo():
    router = Router()
    disponiveis = [{"name": name} for name in (
        "navegar_navegador", "abrir_programa", "listar_janelas_windows",
        "obter_status_windows", "consultar_memoria_persistente",
    )]
    # Sites conhecidos podem usar fast path; a escolha de toolset nao deve
    # classificá-los como aplicativo por conta da palavra "abra".
    assert "apps_files" not in router._detectar_dominios("abra o youtube")
    assert router.select_tool_names("abra o youtube", disponiveis) != ["abrir_programa"]


def test_sim_retoma_acao_original_apos_pergunta_e_nao_relista_janelas():
    harness, executadas, verificados, modelo = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(texto="A Steam nao esta aberta. Quer que eu a abra?"),
        _resposta(_chamada("abrir_programa", '{"programa":"Steam"}')),
        _resposta(texto="Steam iniciada."),
    ])
    _, primeira = harness.processar_mensagem("auren, abra a steam")
    assert primeira.output_text.endswith("?")
    assert harness._pergunta_pendente is not None
    _, segunda = harness.processar_mensagem("sim")
    assert segunda.output_text == "Steam iniciada."
    assert [nome for nome, _ in executadas] == ["listar_janelas_windows", "abrir_programa"]
    assert verificados == ["auren, abra a steam"]
    assert harness.current_task().objective == "auren, abra a steam"
    assert harness.current_task().state is TaskState.COMPLETED
    assert harness._pergunta_pendente is None
    assert len(modelo) == 4


def test_nao_cancela_pendencia_sem_chamar_modelo():
    harness, executadas, _verificados, chamadas_modelo = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(texto="Quer que eu abra a Steam?"),
    ])
    harness.processar_mensagem("abra a steam")
    _, resposta = harness.processar_mensagem("nao")
    assert "nao vou executar" in resposta.output_text
    assert len(chamadas_modelo) == 2
    assert [x[0] for x in executadas] == ["listar_janelas_windows"]
    assert harness._pergunta_pendente is None


def test_sim_solto_nao_dispara_ferramenta():
    harness, executadas, _v, modelo = _harness([])
    _, resposta = harness.processar_mensagem("sim")
    assert "Nao ha uma acao pendente" in resposta.output_text
    assert modelo == []
    assert executadas == []


def test_resposta_a_esclarecimento_do_revisor_preserva_contexto():
    decisoes = iter([
        IntentDecision("esclarecer", "alvo incerto", "Qual aplicativo devo abrir?"),
        IntentDecision("aprovar", "alvo esclarecido"),
    ])
    harness, executadas, verificados, _modelo = _harness([
        _resposta(_chamada("abrir_programa", '{"programa":"Steam"}')),
        _resposta(_chamada("abrir_programa", '{"programa":"Steam"}')),
        _resposta(texto="Steam iniciada."),
    ], verificar=lambda *_: next(decisoes))
    _, pergunta = harness.processar_mensagem("abra o aplicativo")
    assert pergunta.output_text == "Qual aplicativo devo abrir?"
    assert harness._pergunta_pendente is not None
    _, resposta = harness.processar_mensagem("Steam")
    assert resposta.output_text == "Steam iniciada."
    assert [x[0] for x in executadas] == ["abrir_programa"]
    assert verificados[0] == "abra o aplicativo"
    assert "Esclarecimento do usuario: Steam" in verificados[1]


def test_pendencia_nao_sobrevive_ao_fechamento_da_sessao():
    harness, _executadas, _v, _modelo = _harness([
        _resposta(_chamada("listar_janelas_windows")),
        _resposta(texto="Quer que eu abra a Steam?"),
    ])
    harness.processar_mensagem("abra a Steam")
    assert harness._pergunta_pendente is not None
    harness._limpar_estado_sessao()
    assert harness._pergunta_pendente is None


def test_heuristica_nao_conclui_sim_a_partir_de_consulta():
    assert not _pode_encerrar_localmente(
        "sim",
        [{"ferramenta": "listar_janelas_windows", "sucesso": True}],
        visual_mutating_tools=set(),
        terminal_result_tools={"listar_janelas_windows"},
        multitab_concluida=lambda *_args: False,
    )
