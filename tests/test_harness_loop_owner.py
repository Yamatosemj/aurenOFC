"""O Harness e o unico dono do ciclo do agente (modelo -> ferramenta -> modelo -> resposta).

Estes testes fixam o comportamento observavel do ciclo: quando chama o modelo,
quando executa ferramentas, quando continua, quando termina e quando aborta.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import core.harness as harness_module
from core.harness import AurenHarness
from core.task_manager import TaskManager, TaskState
from core.tool_result import ToolResult


def _call(n: int, name: str = "ler_pagina") -> SimpleNamespace:
    return SimpleNamespace(type="function_call", name=name, arguments="{}", call_id=f"c{n}")


def _resp(calls=(), text: str = "", usage: bool = True) -> SimpleNamespace:
    uso = (
        SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            input_tokens_details=SimpleNamespace(cached_tokens=2, cache_write_tokens=0),
        )
        if usage
        else None
    )
    return SimpleNamespace(output=list(calls), output_text=text, usage=uso)


class _Bench:
    """Harness com modelo e executor roteirizados; registra tudo o que o ciclo faz."""

    def __init__(self, model, executor=None, *, max_rounds=None, quick=None, metrics=None):
        self.model_inputs: list = []
        self.model_tool_choices: list = []
        self.tools: list[str] = []
        self._model = model
        self._executor = executor or (lambda _item: "ok")
        kwargs = dict(
            criar_resposta=self._provider,
            executar_ferramenta=self._execute,
            mostrar_uso=lambda: None,
            obter_chamadas=lambda r: [i for i in r.output if getattr(i, "type", "") == "function_call"],
            comando_rapido=(quick(self) if quick else (lambda _m: (False, ""))),
            iniciar_tarefa=lambda: None,
            apos_tarefa=None,
            fechar=lambda: None,
            task_manager=TaskManager(),
            obter_metricas_roteamento=metrics,
        )
        if max_rounds is not None:
            kwargs["max_model_rounds"] = max_rounds
        self.harness = AurenHarness(**kwargs)

    def _provider(self, entrada, response_id=None, reasoning="none", tool_choice=None):
        self.model_inputs.append(entrada)
        self.model_tool_choices.append(tool_choice)
        value = self._model(len(self.model_inputs), self)
        if isinstance(value, Exception):
            raise value
        return value

    def _execute(self, item):
        self.tools.append(item.name)
        value = self._executor(item)
        if isinstance(value, Exception):
            raise value
        return value

    def run(self, objetivo: str):
        tratado, resposta = self.harness.processar_mensagem(objetivo)
        return tratado, resposta, self.harness.current_task()

    @property
    def model_calls(self) -> int:
        return len(self.model_inputs)


# --- terminar corretamente --------------------------------------------------

def test_pergunta_simples_termina_com_uma_chamada_ao_modelo():
    bench = _Bench(lambda n, b: _resp(text="Ola!"))
    tratado, resposta, task = bench.run("oi")
    assert tratado is False
    assert resposta.output_text == "Ola!"
    assert task.state is TaskState.COMPLETED
    assert bench.model_calls == 1
    assert bench.tools == []


def test_pedido_com_uma_ferramenta_termina_quando_o_modelo_responde():
    bench = _Bench(
        lambda n, b: _resp([_call(n)]) if n == 1 else _resp(text="A pagina diz ola."),
        lambda _i: "Texto da pagina",
    )
    _, resposta, task = bench.run("o que diz a pagina atual")
    assert resposta.output_text == "A pagina diz ola."
    assert task.state is TaskState.COMPLETED
    assert bench.tools == ["ler_pagina"]
    assert bench.model_calls == 2
    # A segunda rodada recebe o resultado da ferramenta como function_call_output.
    saida = [i for i in bench.model_inputs[1] if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert saida and saida[0]["output"] == "Texto da pagina"


def test_ferramenta_terminal_conclui_localmente_sem_nova_chamada_ao_modelo():
    bench = _Bench(
        lambda n, b: _resp([_call(n, "obter_status_windows")]),
        lambda _i: ToolResult.success("CPU 10%"),
    )
    _, resposta, task = bench.run("qual o status do windows")
    assert resposta.output_text == "CPU 10%"
    assert task.state is TaskState.COMPLETED
    assert bench.model_calls == 1


def test_pedido_com_varias_acoes_continua_ate_o_modelo_terminar():
    bench = _Bench(
        lambda n, b: _resp([_call(n, "abrir_programa")]) if n <= 3 else _resp(text="Tudo pronto."),
        lambda _i: "aberto",
    )
    _, resposta, task = bench.run("abra o notepad e depois abra a calculadora")
    assert resposta.output_text == "Tudo pronto."
    assert task.state is TaskState.COMPLETED
    assert bench.tools == ["abrir_programa"] * 3
    assert bench.model_calls == 4
    assert [s.success for s in task.steps] == [True, True, True]


def test_varias_ferramentas_na_mesma_rodada_sao_executadas_em_ordem():
    bench = _Bench(
        lambda n, b: _resp([_call(1, "abrir_programa"), _call(2, "focar_janela_windows")]) if n == 1 else _resp(text="ok"),
        lambda _i: "feito",
    )
    _, _, task = bench.run("abra o notepad e depois foque a janela")
    assert bench.tools == ["abrir_programa", "focar_janela_windows"]
    assert task.state is TaskState.COMPLETED
    assert bench.model_calls == 2


# --- limite de rodadas / sem loop infinito -----------------------------------

def test_limite_de_rodadas_padrao_encerra_a_tarefa():
    bench = _Bench(lambda n, b: _resp([_call(n)]))
    _, resposta, task = bench.run("leia a pagina")
    assert task.state is TaskState.FAILED
    assert "limite local de rodadas" in task.error
    assert len(bench.tools) == AurenHarness.DEFAULT_MAX_MODEL_ROUNDS
    assert resposta is not None


def test_limite_configurado_abaixo_do_padrao_e_respeitado():
    bench = _Bench(lambda n, b: _resp([_call(n)]), max_rounds=3)
    _, _, task = bench.run("leia a pagina")
    assert task.state is TaskState.FAILED
    assert len(bench.tools) == 3


def test_objetivo_complexo_eleva_o_limite_acima_do_padrao():
    bench = _Bench(lambda n, b: _resp([_call(n)]))
    _, _, task = bench.run("abra o chrome, pesquise receitas, clique no primeiro, resuma e feche")
    assert task.state is TaskState.FAILED
    assert len(bench.tools) == 18


def test_agente_nunca_roda_alem_do_limite_mesmo_repetindo_a_mesma_chamada():
    repeated = _call(1)
    bench = _Bench(lambda n, b: _resp([repeated]), lambda _i: "mesma coisa")
    _, _, task = bench.run("leia a pagina")
    assert task.state is TaskState.FAILED
    assert len(bench.tools) <= 18
    assert bench.model_calls <= len(bench.tools) + 1


def test_conclusao_local_com_falha_nao_recuperada_nao_reexecuta_a_rodada():
    # Resultado de aparencia "bem-sucedida" para a heuristica local, mas marcado como
    # falha pelo ciclo: antes, o ciclo reexecutava a mesma chamada sem consultar o modelo.
    bench = _Bench(
        lambda n, b: _resp([_call(n, "clicar_elemento")]) if n == 1 else _resp(text="nao deu"),
        lambda _i: "Cliquei em botao X. Acao nao executada",
    )
    _, resposta, task = bench.run("clique no botao")
    assert bench.tools == ["clicar_elemento"]
    assert bench.model_calls == 2
    assert task.state is TaskState.FAILED
    assert task.error == "step_failed_unrecovered"
    assert "falhou sem recuperacao" in resposta.output_text


# --- erros ---------------------------------------------------------------------

def test_excecao_da_ferramenta_vira_falha_e_o_modelo_pode_recuperar():
    chamadas = {"n": 0}

    def executor(_item):
        chamadas["n"] += 1
        return RuntimeError("boom") if chamadas["n"] == 1 else "ok"

    bench = _Bench(
        lambda n, b: _resp([_call(n)]) if n <= 2 else _resp(text="recuperei"),
        executor,
    )
    _, resposta, task = bench.run("leia a pagina")
    assert resposta.output_text == "recuperei"
    assert task.state is TaskState.COMPLETED
    assert [s.success for s in task.steps] == [False, True]
    assert "boom" in task.steps[0].error


def test_falha_de_ferramenta_sem_recuperacao_termina_como_failed():
    bench = _Bench(
        lambda n, b: _resp([_call(n)]) if n == 1 else _resp(text="terminei"),
        lambda _i: ToolResult.failure("Nao consegui ler", error_code="e", tool_name="ler_pagina"),
    )
    _, resposta, task = bench.run("leia a pagina")
    assert task.state is TaskState.FAILED
    assert task.error == "step_failed_unrecovered"
    assert "falhou sem recuperacao" in resposta.output_text


def test_erro_do_provider_em_qualquer_rodada_falha_a_tarefa():
    # primeira rodada
    bench = _Bench(lambda n, b: RuntimeError("down"))
    _, resposta, task = bench.run("oi")
    assert task.state is TaskState.FAILED and task.error == "provider_error: down"
    assert "problema ao acessar o modelo" in resposta.output_text

    # rodada seguinte (depois de uma ferramenta)
    bench = _Bench(lambda n, b: _resp([_call(n)]) if n == 1 else RuntimeError("down2"))
    _, resposta, task = bench.run("leia a pagina")
    assert task.state is TaskState.FAILED and task.error == "provider_error: down2"
    assert bench.tools == ["ler_pagina"]

    # retry de "primeira rodada sem ferramenta"
    bench = _Bench(lambda n, b: _resp(text="nao posso") if n == 1 else RuntimeError("down3"))
    _, _, task = bench.run("abra o notepad")
    assert task.state is TaskState.FAILED and task.error == "provider_error: down3"


def test_retry_de_resposta_vazia_registra_request_e_response_para_medicao(monkeypatch):
    eventos: list[tuple[str, dict]] = []
    monkeypatch.setattr(harness_module, "_write_log", lambda evento, **d: eventos.append((evento, d)))

    bench = _Bench(lambda n, b: _resp(text=""))
    _, _, task = bench.run("oi")

    assert task.state is TaskState.FAILED
    pedidos = [d for e, d in eventos if e == "MODEL_ROUND_REQUEST"]
    respostas = [d for e, d in eventos if e == "MODEL_ROUND_RESPONSE"]

    assert [d["rodada"] for d in pedidos] == [1, 2]
    assert [d["rodada"] for d in respostas] == [1, 2]
    assert pedidos[1]["motivo"] == "empty_response_retry"
    assert respostas[1]["motivo"] == "empty_response_retry"
    assert respostas[1]["uso"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "cached_tokens": 2,
        "cache_write_tokens": 0,
    }


def test_acao_sem_ferramenta_e_resposta_vazia_tem_um_retry_e_depois_falham():
    bench = _Bench(lambda n, b: _resp(text="nao posso"))
    _, resposta, task = bench.run("abra o notepad")
    assert task.error == "action_not_executed" and bench.model_calls == 2
    assert bench.model_tool_choices == ["required", "required"]

    bench = _Bench(lambda n, b: _resp(text=""))
    _, resposta, task = bench.run("oi")
    assert task.error == "empty_response" and bench.model_calls == 2


# --- cancelamento ------------------------------------------------------------------

def test_cancelamento_antes_da_primeira_rodada_nao_chama_o_modelo():
    bench = _Bench(
        lambda n, b: _resp(text="nao deveria"),
        quick=lambda b: (lambda _m: (b.harness.cancel_current_task("teste") and False, "")),
    )
    _, resposta, task = bench.run("oi")
    assert resposta.output_text == "Tarefa cancelada."
    assert task.state is TaskState.CANCELLED
    assert bench.model_calls == 0


def test_cancelamento_durante_a_resposta_do_modelo_impede_novas_ferramentas():
    def model(n, bench):
        if n == 1:
            return _resp([_call(n)])
        bench.harness.cancel_current_task("teste")
        return _resp([_call(n)])

    bench = _Bench(model)
    _, resposta, task = bench.run("leia a pagina")
    assert resposta.output_text == "Tarefa cancelada."
    assert task.state is TaskState.CANCELLED
    assert bench.tools == ["ler_pagina"]  # a ferramenta da rodada 2 nao executou


def test_cancelamento_no_meio_da_rodada_nao_executa_as_chamadas_restantes():
    state = {"n": 0}

    def executor(_item):
        state["n"] += 1
        if state["n"] == 1:
            bench.harness.cancel_current_task("teste")
        return ToolResult.success("ok")

    bench = _Bench(lambda n, b: _resp([_call(1, "abrir_programa"), _call(2, "abrir_programa")]), executor)
    _, resposta, task = bench.run("abra o notepad e a calculadora")
    assert task.state is TaskState.CANCELLED
    assert bench.tools == ["abrir_programa"]
    assert resposta.output_text == "Tarefa cancelada."


def test_cancelamento_apos_a_ferramenta_vence_a_conclusao_local():
    def executor(_item):
        bench.harness.cancel_current_task("teste")
        return ToolResult.success("CPU 10%")

    bench = _Bench(lambda n, b: _resp([_call(n, "obter_status_windows")]), executor)
    _, resposta, task = bench.run("qual o status do windows")
    assert task.state is TaskState.CANCELLED
    assert resposta.output_text == "Tarefa cancelada."


# --- custos / metricas -----------------------------------------------------------------

def test_metricas_de_roteamento_e_uso_continuam_registradas_por_chamada_ao_modelo(monkeypatch):
    eventos: list[tuple[str, dict]] = []
    monkeypatch.setattr(harness_module, "_write_log", lambda evento, **d: eventos.append((evento, d)))
    chamadas_metricas: list[int] = []
    bench = _Bench(
        lambda n, b: _resp([_call(n)]) if n == 1 else _resp(text="fim"),
        lambda _i: "ok",
        metrics=lambda: chamadas_metricas.append(1) or {"dominios": ["x"], "ferramentas": 3},
    )
    _, _, task = bench.run("o que diz a pagina atual")
    assert task.state is TaskState.COMPLETED

    pedidos = [d for e, d in eventos if e == "MODEL_ROUND_REQUEST"]
    respostas = [d for e, d in eventos if e == "MODEL_ROUND_RESPONSE"]
    assert [d["rodada"] for d in pedidos] == [1, 2]
    assert [d["rodada"] for d in respostas] == [1, 2]
    assert len(chamadas_metricas) == bench.model_calls == 2
    for d in respostas:
        assert d["uso"] == {"input_tokens": 10, "output_tokens": 5, "cached_tokens": 2, "cache_write_tokens": 0}
        assert d["router"] == {"dominios": ["x"], "ferramentas": 3}
        assert d["latencia_ms"] >= 0


def test_conclusao_local_continua_emitindo_os_eventos_lidos_pelos_scripts_de_medicao(monkeypatch):
    eventos: list[tuple[str, dict]] = []
    monkeypatch.setattr(harness_module, "_write_log", lambda evento, **d: eventos.append((evento, d)))
    bench = _Bench(
        lambda n, b: _resp([_call(n, "obter_status_windows")]),
        lambda _i: ToolResult.success("CPU 10%"),
    )
    bench.run("qual o status do windows")
    nomes = [e for e, _ in eventos]
    assert "TASK_LOCAL_COMPLETION" in nomes
    fim = [d for e, d in eventos if e == "TASK_END"]
    assert fim and fim[-1]["status"] == "local_completion"


# --- dono unico ------------------------------------------------------------------------------

def test_agent_planner_verifier_reflection_nao_controlam_o_ciclo():
    """Mesmo que o agent/ falhe ao observar, o ciclo termina igual: ele nao decide nada."""
    bench = _Bench(
        lambda n, b: _resp([_call(n, "abrir_programa")]) if n <= 2 else _resp(text="Pronto."),
        lambda _i: "aberto",
    )

    def proibido(*_a, **_k):
        raise AssertionError("o ciclo nao deve consultar o agent/ para decidir")

    for nome in ("observe", "complete", "fail", "cancel"):
        setattr(bench.harness.agent, nome, proibido)
    _, resposta, task = bench.run("abra o notepad e depois abra a calculadora")
    assert resposta.output_text == "Pronto."
    assert task.state is TaskState.COMPLETED


def test_ciclo_tem_um_unico_ponto_de_chamada_ao_modelo_e_nao_toca_no_agent():
    from core import harness_cycle

    fonte = inspect.getsource(harness_cycle.executar_ciclo)
    assert "_chamar_modelo_medido" not in fonte
    assert "harness.criar_resposta" not in fonte
    assert "harness.agent" not in fonte
    assert "harness._pedir_modelo" in fonte
    assert "harness._limite_de_rodadas" in fonte
    assert "range(1, limite_rodadas + 1)" in fonte  # um unico `for` de rodadas
    assert fonte.count("for rodada in") == 1


# --- ToolResult.ok como unica fonte de verdade de sucesso ------------------------------------

def test_toolresult_ok_true_conclui_mesmo_sem_marcador_textual_da_heuristica_antiga():
    """ok=True vence o conteudo: texto sem \"cliquei em\" (ou com a palavra \"erro\") nao reabre a rodada."""
    for texto in ("Acao concluida.", "Cliquei em Salvar sem erro."):
        bench = _Bench(
            lambda n, b: _resp([_call(n, "clicar_elemento")]) if n == 1 else _resp(text="nao deveria chegar aqui"),
            lambda _i, texto=texto: ToolResult.success(texto),
        )
        _, resposta, task = bench.run("clique no botao")
        assert bench.tools == ["clicar_elemento"], texto  # nao repetiu a ferramenta
        assert bench.model_calls == 1, texto  # nao abriu nova rodada por causa da heuristica
        assert task.state is TaskState.COMPLETED, texto
        assert [s.success for s in task.steps] == [True], texto
        assert resposta.output_text != "nao deveria chegar aqui"


def test_toolresult_ok_false_e_falha_mesmo_com_texto_de_sucesso_e_mantem_a_recuperacao():
    # Falha sem recuperacao: continua para o modelo, nunca reexecuta a rodada e termina como failed.
    bench = _Bench(
        lambda n, b: _resp([_call(n, "clicar_elemento")]) if n == 1 else _resp(text="nao deu"),
        lambda _i: ToolResult.failure("Cliquei em botao X", error_code="e", tool_name="clicar_elemento"),
    )
    _, resposta, task = bench.run("clique no botao")
    assert bench.tools == ["clicar_elemento"]
    assert bench.model_calls == 2
    assert [s.success for s in task.steps] == [False]
    assert task.state is TaskState.FAILED
    assert task.error == "step_failed_unrecovered"
    assert "falhou sem recuperacao" in resposta.output_text

    # Falha seguida de sucesso: o ciclo continua e a tarefa se recupera.
    resultados = [
        ToolResult.failure("Cliquei em botao X", error_code="e", tool_name="clicar_elemento"),
        ToolResult.success("Feito.", tool_name="clicar_elemento"),
    ]
    bench = _Bench(
        lambda n, b: _resp([_call(n, "clicar_elemento")]) if n <= 2 else _resp(text="fim"),
        lambda _i: resultados.pop(0),
    )
    _, _resposta, task = bench.run("clique no botao")
    assert bench.tools == ["clicar_elemento", "clicar_elemento"]
    assert [s.success for s in task.steps] == [False, True]
    assert task.state is TaskState.COMPLETED


def test_conclusao_local_usa_apenas_o_campo_sucesso_vindo_de_toolresult_ok():
    def item(texto, sucesso):
        return {"call_id": "c", "ferramenta": "clicar_elemento", "argumentos": "{}",
                "resultado": texto, "sucesso": sucesso}

    assert AurenHarness._pode_encerrar_localmente("clique no botao", [item("qualquer texto", True)])
    assert not AurenHarness._pode_encerrar_localmente("clique no botao", [item("Cliquei em botao X", False)])


def test_nao_existe_segundo_criterio_de_sucesso_concorrendo_com_toolresult_ok():
    assert not hasattr(AurenHarness, "_resultado_indica_sucesso")
    assert "_resultado_indica_sucesso" not in inspect.getsource(harness_module)
    fonte = inspect.getsource(AurenHarness._pode_encerrar_localmente)
    assert 'item.get("sucesso")' in fonte
    assert '["resultado"]' not in fonte  # o texto do resultado nao participa da decisao
