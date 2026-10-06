from __future__ import annotations

import contextvars
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.task_manager import TaskManager, TaskState
from core import usage
from core.task_trace import TaskTrace, TaskTraceStore
from core.tool_result import ToolResult, from_legacy
from agent.orchestrator import AgentOrchestrator
from core.session import SessionContextManager
from skills.loader import SkillLibrary
from core.vision import (
    clear_active_vision_geometry,
    get_active_vision_geometry,
    prepare_vision_result_content,
)
from agent.ari_native.task_queue import AgentTaskQueue


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
# O log canonico de uma conversa fica separado por chat:
#   logs/chats/<chat_id>/chat/chat.log
#
# Isso evita misturar varias conversas no mesmo arquivo e permite localizar
# uma sessao inteira apenas pelo chat_id. Mantemos tambem os arquivos legados
# de logs para compatibilidade com utilitarios antigos da V43.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
CHAT_LOGS_DIR = LOG_DIR / "chats"
TASK_LOG_DIR = LOG_DIR / "tarefas"
LOG_FILE = LOG_DIR / "auren.log"

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
from core.harness_completion import _mensagem_conclusao_local
from core.harness_state import _montar_estado
from core.harness_round_input import _montar_input_da_rodada
from core.harness_heuristics import (
    _parece_tarefa_visual_composta,
    _parece_tarefa_multietapa_browser,
    _parece_tarefa_de_acao,
    _ultima_acao_solicitada,
    _limite_adaptativo,
)
from core.harness_multitab import (
    _extrair_destinos_abas,
    _multitab_concluida,
)


@dataclass(frozen=True)
class SessionContext:
    chat_id: str
    log_file: Path

    @property
    def log_root(self) -> Path:
        return self.log_file.parent.parent


_CURRENT_SESSION: contextvars.ContextVar[SessionContext | None] = contextvars.ContextVar(
    "auren_current_session", default=None
)
_LOG_LOCK = threading.RLock()


def _chat_id() -> str:
    return "chat-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _write_one_log_file(path: Path, event: str, details: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{timestamp}] {event}\n")
        for key, value in details.items():
            arquivo.write(f"  {key}: {_compact_json(value)}\n")


def _create_chat_session() -> SessionContext:
    CHAT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _runtime_redaction_values().clear()
    for _ in range(10):
        chat_id = _chat_id()
        chat_root = CHAT_LOGS_DIR / chat_id
        chat_log_dir = chat_root / "chat"
        try:
            chat_log_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        session = SessionContext(chat_id=chat_id, log_file=chat_log_dir / "chat.log")
        _write_one_log_file(session.log_file, "CHAT_START", {"chat_id": chat_id})
        return session
    raise RuntimeError("Nao foi possivel criar uma pasta unica para o chat atual.")


def start_chat_session() -> str:
    """Cria e vincula uma nova sessao ao contexto de execucao atual."""
    session = _create_chat_session()
    _CURRENT_SESSION.set(session)
    return session.chat_id


def end_chat_session(status: str = "closed") -> None:
    """Fecha a sessao vinculada ao contexto de execucao atual."""
    session = _CURRENT_SESSION.get()
    if session is None:
        return
    try:
        _write_log("CHAT_END", chat_id=session.chat_id, status=status)
    finally:
        _CURRENT_SESSION.set(None)
        _runtime_redaction_values().clear()


def current_chat_id() -> str | None:
    session = _CURRENT_SESSION.get()
    return session.chat_id if session is not None else None


def current_chat_log_path() -> Path | None:
    session = _CURRENT_SESSION.get()
    return session.log_file if session is not None else None


def _prepare_log_details(event: str, details: dict[str, Any]) -> dict[str, Any]:
    """Aplica redacoes especificas de logs sem alterar o comportamento das ferramentas."""
    prepared = dict(details)
    tool_name = str(prepared.get("ferramenta") or "").strip()

    # Registra qualquer texto sensivel presente nos argumentos estruturados antes
    # que eventos futuros possam reproduzi-lo em estado, respostas ou resultados.
    if event == "TOOL_CALL":
        _register_sensitive_values_from_json_text(prepared.get("argumentos"))

    if event == "TOOL_RESULT" and tool_name == "ler_area_transferencia_windows":
        resultado = prepared.get("resultado")
        if resultado is not None:
            texto = str(resultado)
            # O retorno bruto do clipboard nunca deve entrar no arquivo de log.
            if texto and not texto.startswith("[REDACTED clipboard:"):
                _register_redaction_value(texto)
                prepared["resultado"] = f"[REDACTED clipboard: {len(texto)} caracteres]"
            else:
                prepared["resultado"] = "[REDACTED clipboard: conteudo ocultado]"

    return prepared


def _write_log(event: str, **details: Any) -> None:
    try:
        with _LOG_LOCK:
            prepared = _prepare_log_details(event, details)

            # O chat.log canonico pertence a sessao vinculada ao contexto atual.
            session = _CURRENT_SESSION.get()
            if session is not None:
                _write_one_log_file(session.log_file, event, prepared)

            # Mantemos os logs legados da V43 para compatibilidade.
            _write_one_log_file(LOG_FILE, event, prepared)

            task_id = str(prepared.get("task_id") or "").strip()
            if task_id:
                _write_one_log_file(TASK_LOG_DIR / f"{task_id}.txt", event, prepared)
    except OSError:
        # Falha de logging nao pode derrubar uma tarefa do Auren.
        pass


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
        """Decide se podemos evitar uma rodada adicional do modelo."""
        if vision_reobserve_pending:
            return False

        # Tarefas visuais compostas precisam observar o estado novo antes de
        # encerrar. Sem este guard, um clique DOM presente no fim da primeira
        # rodada poderia ser interpretado como a ultima acao e encerrar a tarefa
        # antes da verificacao visual pedida pelo usuario.
        if cls._parece_tarefa_visual_composta(objetivo):
            if any(
                str(item.get("ferramenta", "")) in cls.VISUAL_MUTATING_TOOLS
                and item.get("sucesso")
                for item in resultados_rodada
            ):
                return False

        if cls._parece_tarefa_multietapa_browser(objetivo) and resultados_rodada:
            ultima_listagem = resultados_rodada[-1]
            if (
                ultima_listagem.get("ferramenta") == "listar_abas"
                and ultima_listagem.get("sucesso")
                and cls._multitab_concluida(objetivo, resultados_rodada)
            ):
                return True

        ultima_acao = cls._ultima_acao_solicitada(objetivo)
        if ultima_acao and resultados_rodada:
            ultimo = resultados_rodada[-1]
            if ultimo["ferramenta"] == ultima_acao:
                # Fonte unica de verdade: ToolResult.ok, ja registrado em "sucesso".
                return all(item.get("sucesso") for item in resultados_rodada)

        # Para consultas ou acoes simples, uma unica ferramenta terminal
        # com ToolResult/retorno de sucesso ja e suficiente. So aceitamos
        # isso quando houve exatamente uma chamada nesta rodada e, no caso
        # de leitura, a mensagem original nao parecia uma tarefa de acao.
        if len(resultados_rodada) != 1:
            return False

        ultimo = resultados_rodada[0]
        if not ultimo.get("sucesso"):
            return False

        ferramenta = str(ultimo.get("ferramenta", ""))
        if ferramenta not in cls.TERMINAL_RESULT_TOOLS:
            return False

        somente_leitura = ferramenta in {
            "obter_audio_windows",
            "obter_status_windows",
            "listar_janelas_windows",
            "listar_processos_windows",
            "obter_geometria_janela_windows",
            "ler_area_transferencia_windows",
            "listar_abas",
            "consultar_memoria_persistente",
        }
        if ferramenta == "listar_abas" and cls._parece_tarefa_multietapa_browser(objetivo):
            return False
        if somente_leitura and cls._parece_tarefa_de_acao(objetivo):
            return False
        return True

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
        """Persiste a estratégia sem bloquear o caminho crítico da resposta."""
        if not self.context.persiste or not historico:
            return
        passos = [
            f"{h.get('ferramenta', '')}: {h.get('resultado', '')[:240]}"
            for h in historico
        ]
        # Capturado aqui: o runner roda em outra thread, fora do contexto da sessao.
        chat_id = self._session.chat_id if self._session else None

        def _runner(cancel_event):
            if cancel_event.is_set():
                return {"ok": False, "cancelado": True}
            return self.context.record_strategy(objetivo, passos, resultado, sucesso, chat_id=chat_id)

        try:
            task_id = self._background_queue.submit(
                f"salvar estrategia: {objetivo[:120]}",
                _runner,
                priority=100,
            )