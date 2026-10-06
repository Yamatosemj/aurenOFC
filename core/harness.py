from __future__ import annotations

import contextvars
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.task_manager import TaskManager, TaskState
from core.capabilities import KNOWN_SERVICES
from core import usage
from core.task_trace import TaskTrace, TaskTraceStore
from core.utils import normalizar_nome
from core.tool_result import ToolResult, from_legacy
from agent.orchestrator import AgentOrchestrator
from core.session import SessionContextManager
from skills.loader import SkillLibrary
from core.vision import (
    build_vision_geometry,
    clear_active_vision_geometry,
    get_active_vision_geometry,
    prepare_image_input,
    set_active_vision_geometry,
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


def _chat_id -> str:
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
        texto = str(valor if valor is not None else "")
        texto = texto.replace("\x00", " ")
        texto = texto.strip()

        if len(texto) <= limite:
            return texto

        return texto[:limite] + "\n[resultado truncado pelo harness]"

    @staticmethod
    def _argumentos_da_chamada(item: Any) -> str:
        argumentos = getattr(item, "arguments", "")

        try:
            dados = json.loads(argumentos)
        except (TypeError, json.JSONDecodeError):
            return str(argumentos)

        try:
            return json.dumps(
                _redact_value(dados),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return str(_redact_value(dados))

    @staticmethod
    def _ultima_acao_solicitada(objetivo: str) -> str | None:
        """Retorna apenas a ultima acao terminal explicitamente pedida.

        A heuristica e conservadora: so considera verbos inteiros que
        correspondem a ferramentas que podem ser o ultimo passo de uma
        tarefa. Verbos intermediarios como "abrir" ou "pesquisar" nao
        encerram a tarefa por conta propria.
        """
        import re

        texto = str(objetivo or "").strip().lower()
        if not texto:
            return None

        padroes = {
            "clicar_elemento": ("clica", "clicar", "clique"),
            "preencher_elemento": (
                "preenche", "preencher", "preencha",
                "digita", "digitar", "digite",
            ),
            "pressionar_tecla": (
                "pressiona", "pressionar", "pressione",
                "aperta", "apertar", "aperte",
            ),
            "voltar_pagina": ("volta", "voltar", "volte"),
            "avancar_pagina": ("avanca", "avançar", "avancar", "avance"),
            "recarregar_pagina": ("recarrega", "recarregar", "recarregue"),
            "rolar_pagina": ("rola", "rolar", "role"),
        }

        palavras = re.findall(r"[\wÀ-ÿ]+", texto, flags=re.UNICODE)
        encontrados: list[tuple[int, str]] = []
        for indice, palavra in enumerate(palavras):
            for ferramenta, verbos in padroes.items():
                if palavra in verbos:
                    encontrados.append((indice, ferramenta))

        if not encontrados:
            return None

        return max(encontrados, key=lambda item: item[0])[1]

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
        """Extrai destinos verificáveis para abas numeradas.

        Retorna apenas destinos cujo alvo pode ser comparado de forma segura
        pelo Core: serviços conhecidos ou URLs explícitas.
        """
        texto = str(objetivo or "").strip()
        if not texto:
            return {}

        ordinais = {
            "primeira": 1,
            "segunda": 2,
            "terceira": 3,
            "quarta": 4,
            "quinta": 5,
            "sexta": 6,
            "setima": 7,
            "sétima": 7,
            "oitava": 8,
            "nona": 9,
            "decima": 10,
            "décima": 10,
        }
        destinos: dict[int, str] = {}
        clausulas = re.split(r"\s+e\s+", texto, flags=re.IGNORECASE)
        padrao = re.compile(
            r"^(?:abrir|abre|abra|coloque|coloca|deixe|deixa|carregue|carrega)?\s*"
            r"(?:o|a|um|uma)?\s*(.+?)\s+(?:na|no)\s+"
            r"(primeira|segunda|terceira|quarta|quinta|sexta|setima|sétima|oitava|nona|decima|décima)\s+aba\b",
            flags=re.IGNORECASE,
        )

        for clausula in clausulas:
            match = padrao.search(clausula.strip())
            if not match:
                continue
            bruto = match.group(1).strip(" .,!? ")
            indice = ordinais[normalizar_nome(match.group(2))]

            url = re.search(r"https?://[^\s,;]+", bruto, flags=re.IGNORECASE)
            if url:
                destinos[indice] = url.group(0).rstrip(".,);]")
                continue

            chave = normalizar_nome(bruto)
            conhecido = KNOWN_SERVICES.get(chave)
            if conhecido:
                destinos[indice] = conhecido

        return destinos

    @classmethod
    def _multitab_concluida(cls, objetivo: str, historico: list[dict[str, str]]) -> bool:
        """Confirma destinos de abas numeradas usando o ultimo estado real conhecido."""
        esperados = cls._extrair_destinos_abas(objetivo)
        if not esperados:
            return False

        estado = None
        for item in reversed(historico):
            if str(item.get("ferramenta", "")) == "listar_abas":
                estado = str(item.get("resultado", ""))
                break
        if not estado:
            return False

        for indice, esperado in esperados.items():
            match = re.search(
                rf"(?mi)^Aba\s+{indice}\s*:\s*(.+?)\s*\|\s*(https?://\S+)",
                estado,
            )
            if not match:
                return False

            titulo = match.group(1).strip()
            url_atual = match.group(2).rstrip(".,);]")
            esperado_norm = normalizar_nome(esperado).rstrip("/")
            url_norm = normalizar_nome(url_atual).rstrip("/")
            titulo_norm = normalizar_nome(titulo)

            if esperado_norm.startswith("http://") or esperado_norm.startswith("https://"):
                if not url_norm.startswith(esperado_norm):
                    return False
            else:
                # KNOWN_SERVICES fornece URLs canônicas; o título também conta
                # como evidência auxiliar para páginas que redirecionam.
                if esperado_norm not in url_norm and esperado_norm not in titulo_norm:
                    return False

        return True

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
        """Detecta tarefas visuais que exigem mais de uma observacao/acao."""
        texto = str(objetivo or "").strip().lower()
        if not texto:
            return False

        tem_visao = bool(
            re.search(
                r"\b(?:analise|analisar|veja|ver|olhe|olhar|observe|observar|confira|conferir|localize|localizar)\b.*\b(?:tela|screenshot|captura)\b",
                texto,
                flags=re.IGNORECASE,
            )
        )
        tem_acao_visual = bool(
            re.search(
                r"\b(?:clique|clica|clicar|arraste|arrastar|mova|mover|digite|digitar|pressione|pressionar|selecione|selecionar)\b",
                texto,
                flags=re.IGNORECASE,
            )
        )
        tem_continuacao = bool(
            re.search(
                r"\b(?:depois|em seguida|ent[aã]o|ap[oó]s|posteriormente)\b|\be\s+(?:confirme|verifique|analise|observe|confira)",
                texto,
                flags=re.IGNORECASE,
            )
        )
        return tem_visao and tem_acao_visual and tem_continuacao

    @staticmethod
    def _mensagem_conclusao_local(
        objetivo: str,
        ferramenta: str,
        resultado: str | None = None,
    ) -> str:
        if ferramenta == "listar_abas" and AurenHarness._parece_tarefa_multietapa_browser(objetivo) and resultado:
            return "Concluído: as abas solicitadas foram abertas e verificadas com sucesso."
        if ferramenta in AurenHarness.TERMINAL_RESULT_TOOLS and resultado:
            return str(resultado)

        mensagens = {
            "clicar_elemento": "Concluído: executei o clique solicitado com sucesso.",
            "preencher_elemento": "Concluído: preenchi o campo solicitado com sucesso.",
            "pressionar_tecla": "Concluído: pressionei a tecla solicitada com sucesso.",
            "voltar_pagina": "Concluído: voltei uma página.",
            "avancar_pagina": "Concluído: avancei uma página.",
            "recarregar_pagina": "Concluído: recarreguei a página.",
            "rolar_pagina": "Concluído: rolei a página conforme solicitado.",
        }
        return mensagens.get(
            ferramenta,
            "Concluído: a última ação solicitada foi executada com sucesso.",
        )

    @staticmethod
    def _parece_tarefa_multietapa_browser(objetivo: str) -> bool:
        """Detecta pedidos explicitamente multi-etapa de abas do navegador.

        E um guard local e conservador: serve apenas para impedir que um
        preflight como ``listar_abas`` seja tratado como resultado final.
        """
        texto = str(objetivo or "").strip().lower()
        if not texto or "aba" not in texto:
            return False

        marcadores_de_quantidade = (
            "duas abas", "2 abas", "tres abas", "três abas", "3 abas",
            "segunda aba", "2ª aba", "segunda",
            "terceira aba", "3ª aba", "terceira",
            "quarta aba", "4ª aba", "quarta",
        )
        if not any(marcador in texto for marcador in marcadores_de_quantidade):
            return False

        return any(
            verbo in texto
            for verbo in (
                "abra", "abrir", "abre", "navegue", "navegar",
                "coloque", "deixe", "carregue", "abrindo",
            )
        )

    @staticmethod
    def _parece_tarefa_de_acao(objetivo: str) -> bool:
        """Identifica comandos que claramente pedem uma acao real.

        E um filtro local, barato e conservador: nao chama outra IA para
        decidir se deve usar ferramentas. A exigencia de ferramenta vale
        apenas para a primeira rodada da tarefa.
        """
        texto = str(objetivo or "").strip().lower()
        if not texto:
            return False

        palavras = re.findall(r"[\wÀ-ÿ]+", texto, flags=re.UNICODE)
        while palavras and palavras[0] in {"auren"}:
            palavras.pop(0)
        if not palavras:
            return False

        primeira_palavra = palavras[0]
        verbos_de_acao = {
            "abre", "abrir", "abra",
            "toca", "toque", "tocar",
            "reproduz", "reproduza", "reproduzir",
            "clica", "clicar", "clique",
            "preenche", "preencher",
            "digita", "digitar",
            "pesquisa", "pesquisar",
            "busca", "buscar",
            "navega", "navegar",
            "entra", "entrar",
            "vai", "ir",
            "rola", "rolar",
            "volta", "voltar",
            "avanca", "avançar", "avancar",
            "recarrega", "recarregar",
            "pressiona", "pressionar",
            "fecha", "fechar",
            "define", "definir", "defina",
            "ativa", "ativar", "ative",
            "desativa", "desativar", "desative",
            "muda", "mudar", "mude",
            "ajusta", "ajustar", "ajuste",
            "inspeciona", "inspecionar", "inspecione",
            "procura", "procurar", "procure",
            "localiza", "localizar", "localize",
        }

        return primeira_palavra in verbos_de_acao

    def _montar_estado(
        self,
        objetivo: str,
        historico: list[dict[str, str]],
        resultado_atual: list[dict[str, str]] | None = None,
        incluir_contexto: bool = False,
    ) -> str:
        linhas = [
            "CONTEXTO CONTROLADO DA TAREFA",
            f"Objetivo original: {objetivo}",
        ]

        linhas.append("TIPO: execucao controlada pelo harness")

        if incluir_contexto and self._contexto_tarefa:
            linhas.extend(["", self._contexto_tarefa])

        linhas.extend([
            "",
            "Nao repita uma ferramenta que acabou de executar com sucesso.",
            "EXCECAO VISUAL: em tarefas que exigem verificacao, capturar_tela_windows pode e deve ser chamada novamente depois de uma acao que alterou a tela.",
            "Nunca reutilize coordenadas de uma captura antiga depois de uma acao que possa mover janelas, itens ou o cursor.",
            "Use o ultimo estado conhecido e faca apenas o proximo passo necessario.",
        ])

        if getattr(self, "_vision_reobserve_pending", False):
            linhas.extend([
                "",
                "VERIFICACAO VISUAL PENDENTE: uma acao visual alterou a interface usando o estado de uma captura anterior. Antes de concluir, obtenha uma nova captura da tela ou outro estado confiavel que comprove o resultado.",
            ])

        if historico:
            linhas.extend(["", "Historico recente:"])

            for item in historico[-self.DEFAULT_MAX_HISTORY_ITEMS :]:
                linhas.append(
                    f"- {item['ferramenta']}({item['argumentos']}): "
                    f"{item['resultado']}"
                )

        if resultado_atual:
            linhas.extend(["", "Resultados da rodada anterior:"])

            for item in resultado_atual:
                linhas.append(
                    f"- {item['ferramenta']}({item['argumentos']}): "
                    f"{item['resultado']}"
                )

        estado = "\n".join(linhas)
        return self._texto_seguro(estado, self.MAX_STATE_CHARS)

    def _montar_input_da_rodada(
        self,
        objetivo: str,
        historico: list[dict[str, str]],
        resposta_anterior: Any,
        resultados: list[dict[str, Any]],
    ) -> list[Any]:
        """Monta um input novo sem previous_response_id.

        Mantemos apenas a resposta da rodada anterior e seus outputs,
        incluindo reasoning quando o modelo precisar dele. Nunca reenviamos
        a cadeia inteira da tarefa nem usamos previous_response_id.
        """
        # A rodada atual já será enviada como function_call_output.
        # Não repetimos o mesmo resultado no texto do estado.
        historico_anterior = historico
        if resultados:
            quantidade_atual = len(resultados)
            if quantidade_atual <= len(historico_anterior):
                historico_anterior = historico_anterior[:-quantidade_atual]

        estado = self._montar_estado(
            objetivo,
            historico_anterior,
            incluir_contexto=False,
        )

        input_items: list[Any] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": estado,
                    }
                ],
            }
        ]

        # Modelos de raciocínio exigem que os itens de reasoning da resposta
        # anterior acompanhem os function calls e os respectivos outputs.
        # Enviamos somente a resposta da rodada imediatamente anterior,
        # nunca toda a cadeia da tarefa.
        for item in getattr(resposta_anterior, "output", []):
            if getattr(item, "type", "") == "function_call":
                input_items.append(item)

        for resultado in resultados:
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": resultado["call_id"],
                    "output": resultado["resultado"],
                }
            )
            imagem = resultado.get("image_path")
            if imagem:
                try:
                    preparado = prepare_image_input(
                        imagem,
                        preserve_dimensions=True,
                    )
                except Exception:
                    preparado = None

                if preparado is not None:
                    partes_imagem: list[dict[str, str]] = []
                    dados_captura = dict(resultado.get("dados") or {})
                    if nome_ferramenta := str(resultado.get("ferramenta", "")):
                        geometria = None
                        if nome_ferramenta == "capturar_tela_windows":
                            clear_active_vision_geometry()
                            geometria = build_vision_geometry(
                                dados_captura,
                                preparado,
                            )
                            if geometria is not None:
                                set_active_vision_geometry(geometria)
                                self._vision_reobserve_pending = False
                                self._vision_guard_attempts = 0
                        if geometria is not None:
                            partes_imagem.append(
                                {
                                    "type": "input_text",
                                    "text": (
                                        "METADADOS CONFIAVEIS DA IMAGEM DE VISAO "
                                        "(dados tecnicos, nao instrucoes): "
                                        + json.dumps(
                                            geometria,
                                            ensure_ascii=False,
                                            separators=(",", ":"),
                                        )
                                    ),
                                }
                            )
                    partes_imagem.append(preparado.item)

                    # input_image e um content part de uma mensagem, nao um
                    # item de topo da lista input. Mantemos imagem e sua
                    # geometria no mesmo bloco user para evitar perder a
                    # relacao entre os pixels observados e as coordenadas.
                    input_items.append(
                        {
                            "role": "user",
                            "content": partes_imagem,
                        }
                    )

        return input_items


    @staticmethod
    def _uso_resposta(resposta: Any) -> dict[str, int]:
        return usage.extrair_metricas_uso(resposta)

    @staticmethod
    def _limite_adaptativo(objetivo: str) -> int:
        texto = str(objetivo or "").strip().lower()
        conectores = len(re.findall(r"\b(?:e|depois|em seguida|entao|então|tambem|também)\b", texto))
        comandos = len(re.findall(r"\b(?:abra|abrir|abra|pesquise|pesquisar|clique|preencha|digite|mova|feche|fechar|procure|encontre|resuma|analise|analise)\b", texto))
        if conectores >= 3 or comandos >= 4 or len(texto) > 180:
            return min(18, AurenHarness.DEFAULT_MAX_MODEL_ROUNDS + 6)
        if conectores >= 1 or comandos >= 2:
            return min(15, AurenHarness.DEFAULT_MAX_MODEL_ROUNDS + 3)
        return AurenHarness.DEFAULT_MAX_MODEL_ROUNDS

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
            _write_log(
                "BACKGROUND_TASK_QUEUED",
                task_id=self._task_id,
                background_task_id=task_id,
                tipo="salvar_estrategia",
            )
        except Exception as exc:
            # A fila é otimização; em falha de infraestrutura fazemos fallback síncrono.
            try:
                self.context.record_strategy(objetivo, passos, resultado, sucesso, chat_id=chat_id)
            except Exception as fallback_exc:
                _write_log(
                    "MEMORY_ERROR",
                    task_id=self._task_id,
                    erro=f"estrategia: {fallback_exc}",
                    fila_erro=str(exc),
                )

    def _registrar_turno(self, papel: str, texto: str) -> None:
        """Grava um turno no Session/Context do chat atual (falha nunca derruba a tarefa)."""
        if not self.context.persiste or not str(texto or "").strip():
            return
        try:
            self.context.record_turn(self._session.chat_id if self._session else "", papel, str(texto))
        except Exception as exc:
            _write_log("MEMORY_ERROR", task_id=self._task_id, erro=f"historico_{papel}: {exc}")

    def _garantir_sessao_chat(self) -> str:
        if self._session is None:
            self._session = _create_chat_session()
            self._chat_started_here = True
        else:
            self._chat_started_here = False
        _CURRENT_SESSION.set(self._session)
        return self._session.chat_id

    def _encerrar_sessao_chat(self, status: str = "closed") -> None:
        session = self._session
        if session is None:
            return
        try:
            _write_log("CHAT_END", chat_id=session.chat_id, status=status)
        finally:
            if _CURRENT_SESSION.get() is session:
                _CURRENT_SESSION.set(None)
            self._session = None
            self._chat_started_here = False
            _runtime_redaction_values().clear()


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

        fast_started_perf = time.perf_counter()
        tratado, resposta_rapida = self.comando_rapido(mensagem)
        fast_path_ms = (time.perf_counter() - fast_started_perf) * 1000.0
        if self._trace is not None:
            try:
                self._trace.record_stage(
                    "fast_path",
                    fast_path_ms,
                    category="fast_path",
                    success=bool(tratado),
                )
            except Exception as exc:
                _write_log("TRACE_ERROR", task_id=self._task_id, etapa="fast_path", erro=str(exc))
        if tratado:
            resposta_texto = str(resposta_rapida or "").strip()
            sucesso_fast = resposta_texto and not any(
                marker in resposta_texto.lower()
                for marker in ("acao nao executada", "ação não executada", "nao consegui", "não consegui")
            )
            self.task_manager.begin_step(
                "fast_path",
                str(mensagem or ""),
                task_id=self._task_id,
                step=1,
            )
            self.task_manager.finish_step(
                success=bool(sucesso_fast),
                result=self._texto_seguro(resposta_texto, self.MAX_TOOL_RESULT_CHARS),
                error="" if sucesso_fast else self._texto_seguro(resposta_texto, self.MAX_TOOL_RESULT_CHARS),
                task_id=self._task_id,
            )
            _write_log(
                "TASK_FAST_PATH",
                task_id=self._task_id,
                resultado=resposta_rapida,
                sucesso=bool(sucesso_fast),
            )
            self._registrar_turno("assistant", resposta_texto)
            if not sucesso_fast:
                self.task_manager.fail("fast_path_failed", task_id=self._task_id)
                _write_log("TASK_END", task_id=self._task_id, status="failed", motivo="fast_path_failed")
                return True, _RespostaWrapper(resposta_texto or "Nao foi possivel concluir o comando.")
            if self.task_manager.should_cancel(self._task_id):
                self.task_manager.cancel(task_id=self._task_id, reason="cancelado antes da conclusao do fast path")
                _write_log("TASK_END", task_id=self._task_id, status="cancelled", motivo="fast_path")
                return True, _RespostaWrapper("Tarefa cancelada.")
            if not resposta_texto:
                self.task_manager.fail("empty_response", task_id=self._task_id)
                _write_log("TASK_END", task_id=self._task_id, status="failed", motivo="empty_response")
                return True, _RespostaWrapper("Nao foi possivel produzir uma resposta.")
            self.task_manager.complete(resposta_texto, task_id=self._task_id)
            _write_log("TASK_END", task_id=self._task_id, status="fast_path")
            return True, resposta_rapida

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
        historico: list[dict[str, str]] = []
        resultados_rodada: list[dict[str, str]] = []

        # Se o usuario claramente pediu uma acao, a primeira rodada
        # precisa produzir uma ferramenta. Isso evita uma rodada vazia
        # em que o modelo responde sem executar nada.
        exigir_ferramenta = self._parece_tarefa_de_acao(objetivo)
        empty_response_retries = 0
        falha_nao_recuperada = False
        ferramentas_executadas = 0

        if self.task_manager.should_cancel(self._task_id):
            return self._encerrar_cancelado("cancelado antes da primeira rodada")

        estado_inicial = self._montar_estado(objetivo, historico, incluir_contexto=True)
        self.task_manager.wait_for_model(self._task_id)
        _write_log(
            "MODEL_ROUND_REQUEST",
            task_id=self._task_id,
            rodada=1,
            input_items=1,
            estado_chars=len(estado_inicial),
            tool_choice="required" if exigir_ferramenta else "auto",
        )

        chamada = self._pedir_modelo(estado_inicial, "required" if exigir_ferramenta else None)
        if chamada is None:
            return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
        resposta, latencia_ms, metricas_roteamento = chamada
        self._log_resposta_modelo(1, resposta, latencia_ms, metricas_roteamento)
        self.task_manager.resume(self._task_id)

        limite_rodadas = self._limite_de_rodadas(objetivo)
        if limite_rodadas != self.max_model_rounds:
            _write_log("TASK_ADAPTIVE_DEPTH", task_id=self._task_id, limite_base=self.max_model_rounds, limite_adaptativo=limite_rodadas)
        for rodada in range(1, limite_rodadas + 1):
            chamadas = self.obter_chamadas(resposta)

            if self.task_manager.should_cancel(self._task_id):
                return self._encerrar_cancelado("cancelado durante a tarefa", rodada)

            if not chamadas:
                if exigir_ferramenta and rodada == 1:
                    estado_retry = self._montar_estado(
                        objetivo,
                        historico,
                        [{
                            "ferramenta": "nenhuma",
                            "argumentos": "{}",
                            "resultado": (
                                "A primeira rodada nao executou nenhuma ferramenta. "
                                "Use uma ferramenta agora para iniciar a tarefa."
                            ),
                        }],
                    )
                    _write_log(
                        "MODEL_ROUND_REQUEST",
                        task_id=self._task_id,
                        rodada=2,
                        input_items=1,
                        estado_chars=len(estado_retry),
                        tool_choice="required",
                        motivo="primeira_rodada_sem_ferramenta",
                    )
                    chamada = self._pedir_modelo(estado_retry, "required")
                    if chamada is None:
                        return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
                    resposta, latencia_ms, metricas_roteamento = chamada
                    self._log_resposta_modelo(2, resposta, latencia_ms, metricas_roteamento)
                    continue

                if exigir_ferramenta and ferramentas_executadas == 0:
                    return self._encerrar_falha(
                        "action_not_executed",
                        "Nao consegui executar a acao solicitada.",
                        rodada,
                    )

                if self._vision_reobserve_pending:
                    if self._vision_guard_attempts < 2:
                        self._vision_guard_attempts += 1
                        estado_retry = self._montar_estado(
                            objetivo,
                            historico,
                            [{
                                "ferramenta": "guard_visual_verificacao",
                                "argumentos": "{}",
                                "resultado": (
                                    "A ultima acao visual alterou a interface, mas o resultado final ainda nao foi "
                                    "verificado. Capture a tela novamente ou consulte um estado confiavel antes de concluir."
                                ),
                            }],
                        )
                        _write_log(
                            "TASK_VISUAL_GUARD",
                            task_id=self._task_id,
                            rodada=rodada,
                            tentativa=self._vision_guard_attempts,
                        )
                        self.task_manager.wait_for_model(self._task_id)
                        chamada = self._pedir_modelo(estado_retry, "required")
                        if chamada is None:
                            return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
                        resposta, latencia_ms, metricas_roteamento = chamada
                        self._log_resposta_modelo(
                            rodada + 1,
                            resposta,
                            latencia_ms,
                            metricas_roteamento,
                            motivo="visual_verification_required",
                        )
                        self.task_manager.resume(self._task_id)
                        continue

                    return self._encerrar_falha(
                        "visual_verification_missing",
                        "A tarefa visual nao foi concluida porque a mudanca da interface nao foi verificada.",
                        rodada,
                    )

                if (
                    self._parece_tarefa_multietapa_browser(objetivo)
                    and self._extrair_destinos_abas(objetivo)
                    and not self._multitab_concluida(objetivo, historico)
                    and self._multitab_guard_attempts < 2
                ):
                    self._multitab_guard_attempts += 1
                    estado_retry = self._montar_estado(
                        objetivo,
                        historico,
                        [{
                            "ferramenta": "guard_multitab",
                            "argumentos": "{}",
                            "resultado": (
                                "A tarefa de abas numeradas ainda nao foi comprovadamente concluida. "
                                "Consulte o estado atual com listar_abas e continue executando os destinos pedidos. "
                                "Nao responda como concluido ate que cada aba numerada corresponda ao destino solicitado."
                            ),
                        }],
                    )
                    _write_log(
                        "TASK_MULTITAB_GUARD",
                        task_id=self._task_id,
                        rodada=rodada,
                        tentativa=self._multitab_guard_attempts,
                    )
                    self.task_manager.wait_for_model(self._task_id)
                    chamada = self._pedir_modelo(estado_retry, "required")
                    if chamada is None:
                        return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
                    resposta, latencia_ms, metricas_roteamento = chamada
                    self._log_resposta_modelo(
                        rodada + 1,
                        resposta,
                        latencia_ms,
                        metricas_roteamento,
                        motivo="multitab_incompleta",
                    )
                    self.task_manager.resume(self._task_id)
                    continue

                final_texto = str(getattr(resposta, "output_text", "") or "").strip()
                if falha_nao_recuperada:
                    return self._encerrar_falha(
                        "step_failed_unrecovered",
                        "A tarefa nao foi concluida porque uma etapa falhou sem recuperacao.",
                        rodada,
                    )
                if not final_texto:
                    if empty_response_retries < 1:
                        empty_response_retries += 1
                        estado_retry = self._montar_estado(
                            objetivo,
                            historico,
                            [{
                                "ferramenta": "nenhuma",
                                "argumentos": "{}",
                                "resultado": "A resposta final veio vazia. Responda de forma objetiva ou continue a execucao necessaria.",
                            }],
                        )
                        if self.task_manager.should_cancel(self._task_id):
                            return self._encerrar_cancelado("cancelado antes do retry de resposta vazia", rodada)
                        tool_choice_retry = "required" if exigir_ferramenta else None
                        self.task_manager.wait_for_model(self._task_id)
                        _write_log(
                            "MODEL_ROUND_REQUEST",
                            task_id=self._task_id,
                            rodada=rodada + 1,
                            input_items=1,
                            estado_chars=len(estado_retry),
                            tool_choice=tool_choice_retry,
                            motivo="empty_response_retry",
                        )
                        chamada = self._pedir_modelo(estado_retry, tool_choice_retry)
                        if chamada is None:
                            return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
                        resposta, latencia_ms, metricas_roteamento = chamada
                        self._log_resposta_modelo(
                            rodada + 1,
                            resposta,
                            latencia_ms,
                            metricas_roteamento,
                            motivo="empty_response_retry",
                        )
                        self.task_manager.resume(self._task_id)
                        continue
                    return self._encerrar_falha(
                        "empty_response",
                        "Nao consegui produzir uma resposta final.",
                    )

                extra = None
                if self.apos_tarefa is not None and historico:
                    try:
                        extra = self.apos_tarefa(objetivo, historico)
                    except Exception as erro:
                        _write_log(
                            "MEMORY_ERROR",
                            task_id=self._task_id,
                            erro=str(erro),
                        )
                if extra:
                    texto_final = getattr(resposta, "output_text", "") or ""
                    resposta = _RespostaWrapper(texto_final + str(extra))
                final_texto = str(getattr(resposta, "output_text", "") or "").strip()
                self._salvar_estrategia_em_background(
                    objetivo,
                    historico,
                    final_texto,
                    True,
                )
                self.task_manager.complete(
                    final_texto,
                    task_id=self._task_id,
                )
                self._registrar_turno("assistant", final_texto)
                _write_log(
                    "TASK_STATE",
                    task_id=self._task_id,
                    estado=self.task_manager.current_snapshot().state.value if self.task_manager.current_snapshot() else "completed",
                )
                return False, resposta

            resultados_rodada = []

            for item in chamadas:
                if self.task_manager.should_cancel(self._task_id):
                    return self._encerrar_cancelado("cancelado durante execucao", rodada)

                nome = str(getattr(item, "name", "desconhecida"))
                argumentos = self._argumentos_da_chamada(item)
                self.task_manager.begin_step(
                    nome,
                    argumentos,
                    task_id=self._task_id,
                    step=len(historico) + 1,
                )

                _write_log(
                    "TOOL_CALL",
                    task_id=self._task_id,
                    rodada=rodada,
                    ferramenta=nome,
                    argumentos=argumentos,
                )

                tool_started_perf = time.perf_counter()
                try:
                    resultado_bruto = self.executar_ferramenta(item)
                except Exception as erro:
                    resultado_bruto = ToolResult.failure(
                        f"Falha inesperada no harness: {erro}",
                        error_code="harness_exception",
                        tool_name=nome,
                    )

                # O Dispatcher entrega ToolResult; retornos antigos passam apenas pelo
                # adaptador de compatibilidade. O ciclo nunca decide sucesso olhando
                # para o texto bruto da ferramenta.
                resultado_estruturado = from_legacy(
                    resultado_bruto,
                    tool_name=nome,
                )
                ferramenta_sucesso = resultado_estruturado.ok
                if self._trace is not None:
                    try:
                        self._trace.record_tool(
                            nome,
                            (time.perf_counter() - tool_started_perf) * 1000.0,
                            success=ferramenta_sucesso,
                        )
                    except Exception as exc:
                        _write_log("TRACE_ERROR", task_id=self._task_id, etapa="tool", erro=str(exc))

                if (
                    ferramenta_sucesso
                    and nome != "capturar_tela_windows"
                    and get_active_vision_geometry() is not None
                    and nome in self.VISION_STATE_MUTATING_TOOLS
                ):
                    self._vision_reobserve_pending = True
                    # Uma acao visual invalida o snapshot usado para calcula-la.
                    # Qualquer nova coordenada visual exige uma nova observacao.
                    clear_active_vision_geometry()
                resultado = resultado_estruturado.for_model()
                imagem_path = None
                if isinstance(resultado_estruturado.data, dict):
                    imagem_path = resultado_estruturado.data.get("image_path")

                _write_log(
                    "TOOL_RESULT",
                    task_id=self._task_id,
                    rodada=rodada,
                    ferramenta=nome,
                    resultado=resultado,
                    sucesso=ferramenta_sucesso,
                )

                resultado_compacto = self._texto_seguro(
                    resultado,
                    self.MAX_TOOL_RESULT_CHARS,
                )
                self.task_manager.finish_step(
                    success=ferramenta_sucesso,
                    result=resultado_compacto,
                    error="" if ferramenta_sucesso else resultado_compacto,
                    task_id=self._task_id,
                )
                ferramentas_executadas += 1
                # Falha so deixa de ser "nao recuperada" quando uma chamada posterior tem sucesso.
                falha_nao_recuperada = not ferramenta_sucesso

                historico.append(
                    {
                        "ferramenta": nome,
                        "argumentos": argumentos,
                        "resultado": resultado_compacto,
                    }
                )

                resultados_rodada.append(
                    {
                        "call_id": str(getattr(item, "call_id", "")),
                        "ferramenta": nome,
                        "argumentos": argumentos,
                        "resultado": resultado_compacto,
                        "sucesso": ferramenta_sucesso,
                        "image_path": str(imagem_path) if imagem_path else "",
                        "dados": dict(resultado_estruturado.data or {}),
                    }
                )

            # Se o ultimo passo explicitamente pedido ja foi executado
            # com sucesso, encerramos localmente e economizamos uma chamada
            # adicional ao modelo apenas para ele dizer que terminou.
            # Conclusao local so e permitida sem falha nao recuperada; com
            # falha, o ciclo segue para a proxima rodada do modelo (nunca
            # reexecuta as chamadas da rodada atual).
            if not falha_nao_recuperada and self._pode_encerrar_localmente(
                objetivo,
                resultados_rodada,
                vision_reobserve_pending=self._vision_reobserve_pending,
            ):
                if self.task_manager.should_cancel(self._task_id):
                    return self._encerrar_cancelado("cancelado antes da conclusao local", rodada)
                ferramenta_final = resultados_rodada[-1]["ferramenta"]
                mensagem_final = self._mensagem_conclusao_local(
                    objetivo,
                    ferramenta_final,
                    resultados_rodada[-1].get("resultado"),
                )
                _write_log(
                    "TASK_LOCAL_COMPLETION",
                    task_id=self._task_id,
                    rodada=rodada,
                    ferramenta=ferramenta_final,
                    objetivo=objetivo,
                )
                _write_log(
                    "TASK_END",
                    task_id=self._task_id,
                    status="local_completion",
                    rodada=rodada,
                )
                extra = None
                if self.apos_tarefa is not None:
                    try:
                        extra = self.apos_tarefa(objetivo, historico)
                    except Exception as erro:
                        _write_log(
                            "MEMORY_ERROR",
                            task_id=self._task_id,
                            erro=str(erro),
                        )
                if extra:
                    mensagem_final += str(extra)
                self._salvar_estrategia_em_background(
                    objetivo,
                    historico,
                    mensagem_final,
                    True,
                )
                self.task_manager.complete(
                    mensagem_final,
                    task_id=self._task_id,
                )
                self._registrar_turno("assistant", mensagem_final)
                return False, _RespostaWrapper(mensagem_final)

            # Nova rodada completamente nova: sem previous_response_id.
            proximo_input = self._montar_input_da_rodada(
                objetivo,
                historico,
                resposta,
                resultados_rodada,
            )

            estado_enviado = ""
            if proximo_input and isinstance(proximo_input[0], dict):
                conteudo = proximo_input[0].get("content", [])
                if conteudo and isinstance(conteudo, list):
                    primeiro = conteudo[0]
                    if isinstance(primeiro, dict):
                        estado_enviado = str(primeiro.get("text", ""))

            if self.task_manager.should_cancel(self._task_id):
                return self._encerrar_cancelado("cancelado antes da proxima rodada", rodada)

            self.task_manager.wait_for_model(self._task_id)
            _write_log(
                "MODEL_ROUND_REQUEST",
                task_id=self._task_id,
                rodada=rodada + 1,
                input_items=len(proximo_input),
                estado_chars=len(estado_enviado),
            )
            chamada = self._pedir_modelo(proximo_input)
            if chamada is None:
                return False, _RespostaWrapper(self.MSG_ERRO_PROVIDER)
            resposta, latencia_ms, metricas_roteamento = chamada
            self._log_resposta_modelo(rodada + 1, resposta, latencia_ms, metricas_roteamento)
            self.task_manager.resume(self._task_id)

        self.task_manager.fail(
            "limite local de rodadas do harness atingido",
            task_id=self._task_id,
        )
        _write_log(
            "TASK_END",
            task_id=self._task_id,
            status="max_rounds",
        )
        return False, self._resposta_de_limite(resposta)

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
        if self._trace is not None:
            try:
                self._trace.record_model(
                    rodada,
                    latencia_ms,
                    self._uso_resposta(resposta),
                )
            except Exception as exc:
                _write_log("TRACE_ERROR", task_id=self._task_id, etapa="model", erro=str(exc))
        _write_log(
            "MODEL_ROUND_RESPONSE",
            task_id=self._task_id,
            rodada=rodada,
            output_items=len(getattr(resposta, "output", []) or []),
            output_text=getattr(resposta, "output_text", "") or "",
            uso=self._uso_resposta(resposta),
            latencia_ms=round(latencia_ms, 3),
            router=metricas_roteamento,
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
