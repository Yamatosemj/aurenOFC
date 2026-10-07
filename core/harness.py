from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from core.task_manager import TaskManager, TaskState
from core import usage
from core.task_trace import TaskTrace, TaskTraceStore
from core.tool_result import ToolResult
from agent.orchestrator import AgentOrchestrator
from core.session import SessionContextManager
from skills.loader import SkillLibrary
from core.vision import (
    clear_active_vision_geometry,
    get_active_vision_geometry,
    prepare_vision_result_content,
)
from agent.ari_native.task_queue import AgentTaskQueue

from core.harness_logging import (
    SENSITIVE_KEYS,
    TEXT_SENSITIVE_KEYS,
    USAGE_KEYS,
    _compact_json,
    _redact_value,
    _redact_free_text,
    _register_redaction_value,
    _runtime_redaction_values,
    _register_sensitive_values_from_object,
    _register_sensitive_values_from_json_text,
    _register_redaction_values_from_objective,
)
from core.harness_serialization import (
    _argumentos_da_chamada,
    _texto_seguro,
)
from core.harness_completion import (
    _concluir_tarefa_localmente,
    _finalizar_resposta_sucesso,
    _mensagem_conclusao_local,
    _tentar_retry_resposta_vazia,
)
from core.harness_state import _montar_estado
from core.harness_round_input import (
    _montar_input_da_rodada,
    _montar_input_e_estado_da_rodada,
)
from core.harness_strategy import _salvar_estrategia_em_background as _salvar_estrategia_em_background_impl
from core.harness_turn import _registrar_turno as _registrar_turno_impl
from core.harness_session import (
    _encerrar_sessao_chat as _encerrar_sessao_chat_impl,
    _garantir_sessao_chat as _garantir_sessao_chat_impl,
)
from core.harness_fast_path import _executar_fast_path as _executar_fast_path_impl
from core.harness_model import (
    _executar_rodada_modelo as _executar_rodada_modelo_impl,
    _log_resposta_modelo as _log_resposta_modelo_impl,
)
from core.harness_tools import _executar_chamadas_rodada as _executar_chamadas_rodada_impl
from core.harness_guards import _tratar_rodada_sem_ferramentas as _tratar_rodada_sem_ferramentas_impl
from core.harness_heuristics import (
    _parece_tarefa_visual_composta,
    _parece_tarefa_multietapa_browser,
    _parece_tarefa_de_acao,
    _ultima_acao_solicitada,
    _pode_encerrar_localmente as _pode_encerrar_localmente_impl,
    _limite_adaptativo,
)
from core.harness_multitab import (
    _extrair_destinos_abas,
    _multitab_concluida,
)



from core.harness_runtime import (
    CHAT_LOGS_DIR,
    LOG_DIR,
    LOG_FILE,
    TASK_LOG_DIR,
    _CURRENT_SESSION,
    _LOG_LOCK,
    SessionContext,
    _create_chat_session,
    _write_one_log_file,
    _prepare_log_details,
    _write_log,
    end_chat_session,
    start_chat_session,
    current_chat_id,
    current_chat_log_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from core.harness_cycle import executar_ciclo as _executar_ciclo_impl

class _ContextoLegado(SessionContextManager):
    """DEPRECADO: adapta os callbacks antigos (registrar_conversa/salvar_estrategia).

    So existe para chamadores externos que ainda montam o Harness sem `context=`.
    O fluxo oficial (auren.criar_harness) usa SessionContextManager diretamente.
    """

    def __init__(self, skills, registrar_conversa, salvar_estrategia) -> None:
        super().__init__(store=None, skills=skills, max_chars=2200)
        self._registrar = registrar_conversa
        self._salvar = salvar_estrategia

    @property
    def persiste(self) -> bool:
        return self._registrar is not None or self._salvar is not None

    def record_turn(self, chat_id, papel, conteudo):
        return self._registrar(chat_id, papel, conteudo) if self._registrar is not None else {"ok": False}

    def record_strategy(self, objetivo, passos, resultado, sucesso, chat_id=None):
        # Callbacks legados nao conhecem chat_id: mantemos a assinatura antiga deles.
        return self._salvar(objetivo, passos, resultado, sucesso) if self._salvar is not None else {"ok": False}

    def _render_memoria(self, chat_id, objetivo, turnos):
        hook = getattr(self._salvar, "memory_context", None)
        return (str(hook(objetivo, chat_id or None) or "") if hook else ""), ""


class AurenHarness:
    """Orquestra tarefas sem carregar uma cadeia infinita de contexto.

    Cada rodada do modelo recebe apenas:
    - o objetivo original da tarefa;
    - um estado compacto da execucao;
    - as chamadas de ferramenta da rodada anterior;
    - os resultados dessas chamadas.

    O harness NAO usa previous_response_id. Isso impede que uma tarefa
    carregue toda a arvore anterior de respostas e faz cada rodada partir
    de um contexto pequeno e controlado.
    """

    DEFAULT_MAX_MODEL_ROUNDS = 12
    DEFAULT_MAX_HISTORY_ITEMS = 2
    MAX_TOOL_RESULT_CHARS = 2200
    MAX_STATE_CHARS = 4500

    def __init__(
        self,
        *,
        criar_resposta: Callable[[Any, str | None], Any],
        executar_ferramenta: Callable[[Any], str],
        mostrar_uso: Callable[[], None],
        obter_chamadas: Callable[[Any], list[Any]],
        comando_rapido: Callable[[str], tuple[bool, str]],
        iniciar_tarefa: Callable[[], None],
        apos_tarefa: Callable[[str, list[dict[str, str]]], str | None] | None,
        fechar: Callable[[], None],
        max_model_rounds: int = DEFAULT_MAX_MODEL_ROUNDS,
        task_manager: TaskManager | None = None,
        obter_metricas_roteamento: Callable[[], dict[str, Any]] | None = None,
        registrar_conversa: Callable[[str, str, str], Any] | None = None,
        salvar_estrategia: Callable[[str, list[str], str, bool], Any] | None = None,
        context: SessionContextManager | None = None,
        trace_store: TaskTraceStore | None = None,
    ) -> None:
        if max_model_rounds < 1:
            raise ValueError("max_model_rounds deve ser maior que zero.")

        self.criar_resposta = criar_resposta
        self.executar_ferramenta = executar_ferramenta
        self.mostrar_uso = mostrar_uso
        self.obter_chamadas = obter_chamadas
        self.comando_rapido = comando_rapido
        self.iniciar_tarefa = iniciar_tarefa
        self.apos_tarefa = apos_tarefa
        self.fechar = fechar
        self.max_model_rounds = max_model_rounds
        self.task_manager = task_manager or TaskManager()
        self.obter_metricas_roteamento = obter_metricas_roteamento
        self.registrar_conversa = registrar_conversa
        self.salvar_estrategia = salvar_estrategia
        self.agent = AgentOrchestrator()
        # Session/Context unico: o canal nunca monta contexto; o Harness so consome.
        # Sem `context=`, preservamos o comportamento antigo (skills + callbacks legados).
        if context is None:
            skills = SkillLibrary(PROJECT_ROOT / "skills")
            if registrar_conversa is not None or salvar_estrategia is not None:
                context = _ContextoLegado(skills, registrar_conversa, salvar_estrategia)
            else:
                context = SessionContextManager(skills=skills)
        self.context = context
        self.skill_library = context.skills if context.skills is not None else SkillLibrary(PROJECT_ROOT / "skills")
        self._contexto_tarefa = ""
        self._task_id = ""
        self._session: SessionContext | None = None
        self._session_context_token: contextvars.Token | None = None
        self._chat_started_here = False
        self._multitab_guard_attempts = 0
        self._vision_reobserve_pending = False
        self._vision_guard_attempts = 0
        # O Ari usa uma fila de prioridade para tarefas de fundo. No Auren ela
        # fica restrita a aprendizado/persistencia pos-tarefa para não atrasar a resposta.
        self._background_queue = AgentTaskQueue(max_workers=1, max_results=100)
        self.trace_store = trace_store or TaskTraceStore()
        self._trace: TaskTrace | None = None
        self._trace_started_perf: float | None = None

    @staticmethod
    def _texto_seguro(valor: Any, limite: int) -> str:
        return _texto_seguro(valor, limite)

    @staticmethod
    def _argumentos_da_chamada(item: Any) -> str:
        return _argumentos_da_chamada(item)

    @staticmethod
    def _ultima_acao_solicitada(objetivo: str) -> str | None:
        return _ultima_acao_solicitada(objetivo)

    TERMINAL_RESULT_TOOLS = {
        # Leituras/resultados autoexplicativos: uma unica chamada bem-sucedida
        # ja produz uma resposta utilizavel pelo usuario.
        "obter_audio_windows",
        "obter_status_windows",
        "listar_janelas_windows",
        "listar_processos_windows",
        "obter_geometria_janela_windows",
        "ler_area_transferencia_windows",
        "listar_abas",
        "consultar_memoria_persistente",
        # Alteracoes simples cujo retorno ja confirma a acao.
        "definir_volume_windows",
        "definir_mudo_windows",
        "controle_midia_windows",
        "focar_janela_windows",
        "minimizar_janela_windows",
        "maximizar_janela_windows",
        "restaurar_janela_windows",
        "mover_janela_windows",
        "redimensionar_janela_windows",
    }

    @staticmethod
    def _extrair_destinos_abas(objetivo: str) -> dict[int, str]:
        return _extrair_destinos_abas(objetivo)

    @classmethod
    def _pode_encerrar_localmente(
        cls,
        objetivo: str,
        resultados_rodada: list[dict[str, Any]],
        *,
        vision_reobserve_pending: bool = False,
    ) -> bool:
        # O critério visível de sucesso continua sendo `item.get("sucesso")`,
        # conforme o contrato de ToolResult preservado pelo wrapper.
        return _pode_encerrar_localmente_impl(
            objetivo,
            resultados_rodada,
            vision_reobserve_pending=vision_reobserve_pending,
            visual_mutating_tools=cls.VISUAL_MUTATING_TOOLS,
            terminal_result_tools=cls.TERMINAL_RESULT_TOOLS,
            multitab_concluida=cls._multitab_concluida,
        )

    VISION_STATE_MUTATING_TOOLS = {
        "clicar_mouse_windows",
        "arrastar_mouse_windows",
        "mover_mouse_windows",
        "pressionar_tecla_windows",
        "clicar_elemento_windows",
        "preencher_elemento_windows",
        "alternar_elemento_windows",
        "selecionar_elemento_windows",
        "clicar_elemento",
        "preencher_elemento",
        "pressionar_tecla",
        "rolar_pagina",
    }

    VISUAL_MUTATING_TOOLS = {
        # Acoes que podem alterar a imagem da tela ou a posicao dos elementos.
        "clicar_mouse_windows",
        "arrastar_mouse_windows",
        "mover_mouse_windows",
        "pressionar_tecla_windows",
        "clicar_elemento_windows",
        "preencher_elemento_windows",
        "alternar_elemento_windows",
        "selecionar_elemento_windows",
    }

    @staticmethod
    def _parece_tarefa_visual_composta(objetivo: str) -> bool:
        return _parece_tarefa_visual_composta(objetivo)

    @staticmethod
    def _mensagem_conclusao_local(
        objetivo: str,
        ferramenta: str,
        resultado: str | None = None,
    ) -> str:
        return _mensagem_conclusao_local(
            objetivo,
            ferramenta,
            resultado,
            terminal_result_tools=AurenHarness.TERMINAL_RESULT_TOOLS,
            multietapa_browser=AurenHarness._parece_tarefa_multietapa_browser(objetivo),
        )

    @staticmethod
    def _parece_tarefa_multietapa_browser(objetivo: str) -> bool:
        return _parece_tarefa_multietapa_browser(objetivo)

    @classmethod
    def _multitab_concluida(cls, objetivo: str, historico: list[dict[str, str]]) -> bool:
        return _multitab_concluida(objetivo, historico)

    @staticmethod
    def _parece_tarefa_de_acao(objetivo: str) -> bool:
        return _parece_tarefa_de_acao(objetivo)

    def _montar_estado(
        self,
        objetivo: str,
        historico: list[dict[str, str]],
        resultado_atual: list[dict[str, str]] | None = None,
        incluir_contexto: bool = False,
    ) -> str:
        return _montar_estado(
            objetivo,
            historico,
            resultado_atual,
            incluir_contexto=incluir_contexto,
            contexto_tarefa=self._contexto_tarefa,
            vision_reobserve_pending=getattr(self, "_vision_reobserve_pending", False),
            max_history_items=self.DEFAULT_MAX_HISTORY_ITEMS,
            max_state_chars=self.MAX_STATE_CHARS,
            texto_seguro=self._texto_seguro,
        )

    def _montar_input_da_rodada(
        self,
        objetivo: str,
        historico: list[dict[str, str]],
        resposta_anterior: Any,
        resultados: list[dict[str, Any]],
    ) -> list[Any]:
        return _montar_input_da_rodada(
            objetivo,
            historico,
            resposta_anterior,
            resultados,
            montar_estado=self._montar_estado,
            preparar_resultado_visual=prepare_vision_result_content,
            ao_atualizar_geometria=self._marcar_geometria_visual_atualizada,
        )

    def _marcar_geometria_visual_atualizada(self) -> None:
        self._vision_reobserve_pending = False
        self._vision_guard_attempts = 0

    @staticmethod
    def _uso_resposta(resposta: Any) -> dict[str, int]:
        return usage.extrair_metricas_uso(resposta)

    @staticmethod
    def _limite_adaptativo(objetivo: str) -> int:
        return _limite_adaptativo(objetivo, AurenHarness.DEFAULT_MAX_MODEL_ROUNDS)

    def _chamar_modelo_medido(self, *args: Any, **kwargs: Any) -> tuple[Any, float, dict[str, Any]]:
        """Executa uma chamada real ao modelo e mede somente sua latencia.

        A coleta de metricas e observacional: nao altera argumentos, resposta ou
        fluxo de execucao.
        """
        inicio = time.perf_counter()
        resposta = self.criar_resposta(*args, **kwargs)
        latencia_ms = (time.perf_counter() - inicio) * 1000.0

        metricas: dict[str, Any] = {}
        callback = self.obter_metricas_roteamento
        if callback is not None:
            try:
                valor = callback()
                if isinstance(valor, dict):
                    metricas = dict(valor)
            except Exception:
                # Instrumentacao nunca pode derrubar a tarefa real.
                metricas = {}
        return resposta, latencia_ms, metricas

    def _salvar_estrategia_em_background(
        self,
        objetivo: str,
        historico: list[dict[str, str]],
        resultado: str,
        sucesso: bool = True,
    ) -> None:
        _salvar_estrategia_em_background_impl(
            objetivo,
            historico,
            resultado,
            sucesso,
            context=self.context,
            background_queue=self._background_queue,
            task_id=self._task_id,
            chat_id=self._session.chat_id if self._session else None,
            write_log=_write_log,
        )

    def _registrar_turno(self, papel: str, texto: str) -> None:
        _registrar_turno_impl(
            papel,
            texto,
            context=self.context,
            chat_id=self._session.chat_id if self._session else "",
            task_id=self._task_id,
            write_log=_write_log,
        )

    def _garantir_sessao_chat(self) -> str:
        (
            self._session,
            self._chat_started_here,
            chat_id,
        ) = _garantir_sessao_chat_impl(
            self._session,
            criar_sessao=_create_chat_session,
            definir_sessao_atual=_CURRENT_SESSION.set,
        )
        return chat_id

    def _encerrar_sessao_chat(self, status: str = "closed") -> None:
        _encerrar_sessao_chat_impl(
            self._session,
            status,
            obter_sessao_atual=_CURRENT_SESSION.get,
            limpar_sessao_atual=lambda: _CURRENT_SESSION.set(None),
            limpar_estado_harness=self._limpar_estado_sessao,
            limpar_redaction=_runtime_redaction_values().clear,
            write_log=_write_log,
        )

    def _limpar_estado_sessao(self) -> None:
        self._session = None
        self._chat_started_here = False


    def _processar_mensagem_impl(self, mensagem: str) -> tuple[bool, Any]:
        """Retorna (tratado_rapido, resposta)."""
        self._garantir_sessao_chat()
        self._trace_started_perf = time.perf_counter()
        context_started_perf = self._trace_started_perf
        self.iniciar_tarefa()
        clear_active_vision_geometry()
        self._multitab_guard_attempts = 0
        self._vision_reobserve_pending = False
        self._vision_guard_attempts = 0
        objetivo_log = mensagem.strip()
        try:
            plan = self.agent.begin(objetivo_log)
            chat_id = self._session.chat_id if self._session else ""
            contexto = self.context.build(
                chat_id,
                objetivo_log,
                tarefas=self.task_manager.recent_snapshots(chat_id, limit=3),
            )
            for erro_contexto in contexto.erros:
                _write_log("CONTEXT_ERROR", objetivo=objetivo_log, erro=erro_contexto)
            self._contexto_tarefa = contexto.texto
        except Exception as exc:
            _write_log("AGENT_INIT_ERROR", objetivo=objetivo_log, erro=str(exc))
            plan = None
            self._contexto_tarefa = ""
        context_ms = (time.perf_counter() - context_started_perf) * 1000.0
        if self._contexto_tarefa:
            self._contexto_tarefa = self._texto_seguro(self._contexto_tarefa, self.context.max_chars)
        task_snapshot = self.task_manager.create(
            objetivo_log,
            chat_id=self._session.chat_id if self._session else None,
        )
        self._task_id = task_snapshot.task_id
        self.task_manager.start(self._task_id)
        try:
            self._trace = self.trace_store.start_task(
                task_id=self._task_id,
                chat_id=self._session.chat_id if self._session else None,
                objective=objetivo_log,
                started_at=task_snapshot.created_at,
                started_perf=self._trace_started_perf,
            )
            self._trace.record_stage(
                "contexto",
                context_ms,
                category="context",
                metadata={"objective_chars": len(objetivo_log)},
            )
        except Exception as exc:
            self._trace = None
            _write_log("TRACE_ERROR", task_id=self._task_id, etapa="start", erro=str(exc))
        _register_redaction_values_from_objective(objetivo_log)
        _write_log(
            "TASK_START",
            task_id=self._task_id,
            objetivo=objetivo_log,
        )
        self._registrar_turno("user", objetivo_log)

        fast_path = _executar_fast_path_impl(
            mensagem,
            comando_rapido=self.comando_rapido,
            task_manager=self.task_manager,
            task_id=self._task_id,
            trace=self._trace,
            max_tool_result_chars=self.MAX_TOOL_RESULT_CHARS,
            texto_seguro=self._texto_seguro,
            registrar_turno=self._registrar_turno,
            write_log=_write_log,
            resposta_wrapper=_RespostaWrapper,
        )
        if fast_path is not None:
            return fast_path

        return self._executar_ciclo(mensagem.strip())

    # ------------------------------------------------------------------
    # CICLO DO AGENTE
    # ------------------------------------------------------------------
    # DONO UNICO: este metodo. Quem decide se o Auren continua pensando /
    # executando ou termina e o Harness, aqui, e em nenhum outro lugar.
    #
    #   modelo decide -> (ferramentas? executa -> modelo decide de novo) -> resposta
    #
    # Quem decide cada coisa:
    #   chamar o modelo ........ `_pedir_modelo` (unico ponto; erro do provider encerra a tarefa)
    #   executar ferramenta .... o modelo pede (obter_chamadas); o ciclo executa (executar_ferramenta)
    #   continuar outra rodada . o ciclo: houve chamadas e `_pode_encerrar_localmente` nao concluiu
    #   finalizar .............. o modelo respondeu sem chamadas, ou `_pode_encerrar_localmente`
    #   abortar / falhar ....... `_encerrar_cancelado`, `_encerrar_falha`, erro do provider
    #                            e `_limite_de_rodadas`
    #
    # Planner/Verifier/Reflection (agent/) NAO participam do ciclo. O unico
    # dado que o Harness consome de agent/ e a estimativa de profundidade do
    # Planner (plan.max_rounds), usada por `_limite_de_rodadas`.
    def _executar_ciclo(self, objetivo: str) -> tuple[bool, Any]:
        return _executar_ciclo_impl(self, objetivo, _RespostaWrapper, _write_log)
    # --- Mecanica do ciclo (nao decide nada; so executa o que o ciclo decidiu) ---

    MSG_ERRO_PROVIDER = "Tive um problema ao acessar o modelo. A tarefa nao foi concluida."

    def _limite_de_rodadas(self, objetivo: str) -> int:
        """Unica fonte do limite de rodadas do ciclo.

        `max_model_rounds` abaixo do padrao e um teto rigido do chamador. A partir
        do padrao, objetivos longos/compostos podem elevar o limite (profundidade
        adaptativa local ou estimativa do Planner), nunca reduzi-lo.
        """
        if self.max_model_rounds < self.DEFAULT_MAX_MODEL_ROUNDS:
            return self.max_model_rounds
        plano = getattr(getattr(self.agent, "state", None), "plan", None)
        return max(
            self.max_model_rounds,
            self._limite_adaptativo(objetivo),
            int(getattr(plano, "max_rounds", 0) or 0),
        )

    def _pedir_modelo(self, entrada: Any, tool_choice: str | None = None) -> tuple[Any, float, dict[str, Any]] | None:
        """Unico ponto de chamada ao modelo do ciclo.

        Se o provider falhar, a tarefa e marcada como failed e retorna None; o
        ciclo apenas devolve a mensagem de erro ao usuario.
        """
        argumentos = (entrada, None, "none") + ((tool_choice,) if tool_choice is not None else ())
        try:
            return self._chamar_modelo_medido(*argumentos)
        except Exception as exc:
            snapshot = self.task_manager.current_snapshot()
            if snapshot is not None and snapshot.state not in {
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
            }:
                self.task_manager.fail(f"provider_error: {exc}", task_id=self._task_id)
            _write_log("PROVIDER_ERROR", task_id=self._task_id, erro=str(exc))
            return None

    def _log_resposta_modelo(
        self,
        rodada: int,
        resposta: Any,
        latencia_ms: float,
        metricas_roteamento: dict[str, Any],
        **extra: Any,
    ) -> None:
        _log_resposta_modelo_impl(
            rodada,
            resposta,
            latencia_ms,
            metricas_roteamento,
            trace=self._trace,
            task_id=self._task_id,
            uso_resposta=self._uso_resposta,
            write_log=_write_log,
            **extra,
        )

    def _encerrar_cancelado(self, motivo: str, rodada: int | None = None) -> tuple[bool, Any]:
        self.task_manager.cancel(task_id=self._task_id, reason=motivo)
        detalhes = {"rodada": rodada} if rodada is not None else {}
        _write_log("TASK_END", task_id=self._task_id, status="cancelled", **detalhes)
        return False, _RespostaWrapper("Tarefa cancelada.")

    def _encerrar_falha(self, codigo: str, mensagem: str, rodada: int | None = None) -> tuple[bool, Any]:
        self.task_manager.fail(codigo, task_id=self._task_id)
        detalhes = {"rodada": rodada} if rodada is not None else {}
        _write_log("TASK_END", task_id=self._task_id, status="failed", motivo=codigo, **detalhes)
        return False, _RespostaWrapper(mensagem)

    def processar_mensagem(self, mensagem: str) -> tuple[bool, Any]:
        """Executa uma tarefa com isolamento de falha e ciclo de vida rastreado."""
        self._garantir_sessao_chat()
        token = _CURRENT_SESSION.set(self._session)
        try:
            return self._processar_mensagem_impl(mensagem)
        except Exception as erro:
            try:
                snapshot = self.task_manager.current_snapshot()
                if snapshot is not None and snapshot.state not in {
                    TaskState.COMPLETED,
                    TaskState.FAILED,
                    TaskState.CANCELLED,
                }:
                    self.task_manager.fail(str(erro))
                    _write_log(
                        "TASK_EXCEPTION",
                        task_id=snapshot.task_id,
                        erro=str(erro),
                    )
                    _write_log(
                        "TASK_END",
                        task_id=snapshot.task_id,
                        status="failed",
                    )
            except Exception:
                pass
            raise
        finally:
            try:
                trace = self._trace
                if trace is not None:
                    snapshot = self.task_manager.current_snapshot()
                    status = snapshot.state.value if snapshot is not None else "failed"
                    error = snapshot.error if snapshot is not None else ""
                    total_ms = (
                        (time.perf_counter() - self._trace_started_perf) * 1000.0
                        if self._trace_started_perf is not None
                        else None
                    )
                    trace.finish(
                        status=status,
                        error=error,
                        total_ms=total_ms,
                    )
            except Exception as trace_error:
                _write_log(
                    "TRACE_ERROR",
                    task_id=self._task_id,
                    etapa="finish",
                    erro=str(trace_error),
                )
            finally:
                self._trace = None
                self._trace_started_perf = None
                _CURRENT_SESSION.reset(token)

    def current_task(self):
        """Retorna um snapshot imutavel da tarefa atual, se existir."""
        return self.task_manager.current_snapshot()

    def cancel_current_task(self, reason: str = "cancelado pelo usuario") -> bool:
        """Solicita cancelamento cooperativo da tarefa em andamento."""
        snapshot = self.task_manager.current_snapshot()
        if snapshot is None or snapshot.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            return False
        self.task_manager.request_cancel(snapshot.task_id)
        _write_log(
            "TASK_CANCEL_REQUESTED",
            task_id=snapshot.task_id,
            motivo=reason,
        )
        return True

    @staticmethod
    def _resposta_de_limite(resposta: Any) -> Any:
        # Mantem o objeto de resposta para o chamador, mas o texto pode
        # continuar sendo usado normalmente pelo Auren.
        try:
            texto = getattr(resposta, "output_text", "") or ""
            if texto.strip():
                # Alguns modelos podem responder sem perceber que o loop
                # terminou; informamos isso explicitamente no texto local.
                return _RespostaWrapper(
                    texto +
                    "\nInterrompi a tarefa porque o limite local de rodadas do harness foi atingido."
                )
        except Exception:
            pass

        return resposta

    def executar(self) -> None:
        print("Digite 'sair' para encerrar.\n")

        self._garantir_sessao_chat()
        token = _CURRENT_SESSION.set(self._session)
        try:
            while True:
                mensagem = input("Você: ")

                if not mensagem.strip():
                    continue

                if mensagem.lower().strip() == "sair":
                    print("Auren: Ate mais.")
                    break

                tratado, resposta = self.processar_mensagem(mensagem)

                if tratado:
                    texto = resposta
                else:
                    texto = getattr(resposta, "output_text", str(resposta))

                print("Auren:", texto)
                self.mostrar_uso()

        finally:
            try:
                try:
                    self._background_queue.shutdown(cancel_pending=False)
                except Exception:
                    pass
                self.fechar()
            finally:
                self._encerrar_sessao_chat("closed")
                _CURRENT_SESSION.reset(token)


class _RespostaWrapper:
    """Wrapper minimo para preservar o contrato output_text do Auren."""

    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
