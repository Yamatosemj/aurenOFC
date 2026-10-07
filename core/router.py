"""Router: dono UNICO da selecao de acao do Auren.

DONO:           Router (este modulo).
LUGAR NO FLUXO: pedido -> [experimento de audio, so com flag] -> Router.decidir_local()
                (atalho deterministico, executado por tools/fast_paths.py)
                -> sem atalho: Router.select_tools() restringe as ferramentas e o
                modelo escolhe entre elas (core/orchestrator.py).
ABSORVEU:       as regex de atalho que tools/fast_paths.py duplicava; as regras vivem em
                core/local_decision.py e sao acessadas, em runtime, SOMENTE por aqui.
NAO E DONO:     LLMRouter/brains fast|deep (perfil do modelo, sem efeito na escolha de
                ferramenta) e CapabilityResolver/TaskSpec (so atras da flag experimental).
Executores (fast_paths, dispatcher, PermissionManager) nunca decidem; so executam.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.capability_resolver import CapabilityResolution, CapabilityResolver
from core.local_decision import DecisionResult, LocalDecisionEngine


# Ferramentas de ancoragem que ajudam em tarefas curtas sem obrigar o modelo a
# receber o registry inteiro. Em tarefas ambíguas o Router simplesmente devolve
# todas as ferramentas, preservando a compatibilidade da V43.
COMMON_TOOLS = {
    "consultar_memoria_persistente",
    "listar_memoria",
    "obter_status_windows",
    "listar_janelas_windows",
}

TOOL_GROUPS = {
    "browser": {
        "navegar_navegador",
        "obter_contexto_navegador",
        "ler_pagina",
        "clicar_elemento",
        "preencher_elemento",
        "pressionar_tecla",
        "listar_abas",
        "abrir_nova_aba",
        "trocar_aba",
        "fechar_aba",
        "voltar_pagina",
        "avancar_pagina",
        "recarregar_pagina",
        "rolar_pagina",
    },
    "windows": {
        "listar_janelas_windows",
        "focar_janela_windows",
        "minimizar_janela_windows",
        "maximizar_janela_windows",
        "obter_geometria_janela_windows",
        "mover_janela_windows",
        "redimensionar_janela_windows",
        "restaurar_janela_windows",
        "fechar_janela_windows",
    },
    "uia": {
        "inspecionar_interface_windows",
        "clicar_elemento_windows",
        "preencher_elemento_windows",
        "alternar_elemento_windows",
        "selecionar_elemento_windows",
    },
    "audio": {
        "obter_audio_windows",
        "definir_volume_windows",
        "definir_mudo_windows",
        "controle_midia_windows",
    },
    "clipboard": {
        "ler_area_transferencia_windows",
        "definir_area_transferencia_windows",
    },
    "input": {
        "pressionar_tecla_windows",
        "mover_mouse_windows",
        "clicar_mouse_windows",
        "arrastar_mouse_windows",
    },
    "process": {
        "listar_processos_windows",
        "encerrar_processo_windows",
    },
    "system": {
        "obter_status_windows",
    },
    "vision": {
        "capturar_tela_windows",
    },
    "apps_files": {
        "abrir_programa",
        "buscar_arquivo",
        "inspecionar_arquivo",
        "ler_arquivo",
    },
    "spotify_desktop": {
        "abrir_programa",
        "listar_janelas_windows",
        "focar_janela_windows",
        "inspecionar_interface_windows",
        "clicar_elemento_windows",
        "preencher_elemento_windows",
        "pressionar_tecla_windows",
        "controle_midia_windows",
    },
    "memory": {
        "salvar_memoria_persistente",
        "consultar_memoria_persistente",
        "listar_memoria",
        "esquecer_memoria_persistente",
    },
}

# Frases suficientemente específicas para evitar que o Router corte uma
# ferramenta necessária. Termos ambíguos como "abrir" ou "clicar" sozinhos
# nunca acionam uma rota especializada.
DOMAIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "spotify_desktop": (
        r"\b(?:toc(?:ar|e|a)|toqu(?:e|em)|reproduz(?:ir|a)|execute|executa)\b.*\bspotify\b",
        r"\bspotify\b.*\b(?:toc(?:ar|e|a)|toqu(?:e|em)|reproduz(?:ir|a)|playlist|m[uú]sica)\b",
        r"\bspotify\b.*\b(?:toque|tocar|reproduzir)\b",
    ),
    "browser": (
        r"\bnavegador\b",
        r"\baba(s)?\b",
        r"\bsite\b",
        r"\bp[aá]gina\b",
        r"\burl\b",
        r"\blink\b",
        r"\byoutube\b",
        r"\bdiscord\b",
        r"\bgoogle\b",
        r"\bspotify\b",
        r"\bchrome\b",
        r"\bedge\b",
        r"\bpesquis[ae](r)?\b.*\b(no|na|pelo|pelo)\b",
        r"\bpesquis[ae](r)?\b.*\bm[uú]sica\b",
    ),
    "windows": (
        r"\bjanela(s)?\b",
        r"\bminimiz",
        r"\bmaximiz",
        r"\brestaur",
        r"\bmover\b.*\bjanela",
        r"\bredimension",
        r"\bposi[cç][aã]o\b.*\bjanela",
        r"\btamanho\b.*\bjanela",
    ),
    "uia": (
        r"\buia\b",
        r"\bautomationid\b",
        r"\binspecion(?:ar|e|a|ou)\b.*\binterface\b",
        r"\binterface\b.*\b(janela|controle|elemento)\b",
        r"\binterface\b.*\bwindows\b",
        r"\bcheckbox\b",
        r"\bcaixa de sele[cç][aã]o\b",
        r"\bmarque(m)?\b.*\bcaixa\b",
        r"\bdesmarque(m)?\b.*\bcaixa\b",
        r"\bmarc(ar|ado|ada|e)\b.*\bcheckbox\b",
        r"\bcampo\b.*\bpreench",
        r"\bpreench.*\bcampo\b",
        r"\bbot[aã]o\b.*\bjanela\b",
        r"\bcontrole\b.*\bjanela\b",
        r"\bselecion[ae](r)?\b.*\b(op[cç][aã]o|item|lista)\b",
    ),
    "vision": (
        r"\b(?:capturar|tire|tirar|faca|fazer)\b.*\b(?:tela|screenshot|captura)\b",
        r"\b(?:analise|analisar|veja|ver)\b.*\b(?:tela|screenshot|captura)\b",
    ),
    "audio": (
        r"\bvolume\b",
        r"\bmudo\b",
        r"\bsom\b",
        r"\baudio\b",
        r"\bplay\s*/?\s*pause\b",
        r"\bpr[oó]xima\b.*\bm[uú]sica",
        r"\banterior\b.*\bm[uú]sica",
        r"\bm[ií]dia\b",
    ),
    "clipboard": (
        r"\b[aá]rea de transfer[eê]ncia\b",
        r"\bclipboard\b",
    ),
    "input": (
        r"\bmouse\b",
        r"\barrast\w*\b",
        r"\bsolt\w*\b.*\b(?:mouse|arquivo|item|pasta|janela)\b",
        r"\bteclado\b",
        r"\btecla\b",
        r"\bclicar\b.*\b(x|y)\s*=",
        r"\bclique\b.*\bcoordenad",
    ),
    "process": (
        r"\bprocesso(s)?\b",
        r"\bpid\b",
        r"\btaskkill\b",
        r"\bencerrar\b.*\bprocesso",
        r"\bmat(ar|e|ou)\b.*\bprocesso",
    ),
    "system": (
        r"\bhora\b",
        r"\bdata\b.*\bhoje\b",
        r"\bram\b",
        r"\bmem[oó]ria\b.*\b(uso|usada|utilizada)\b",
        r"\btempo\b.*\b(ligado|ligad[oó]|computador)",
        r"\bh[aá] quanto tempo.*\bcomputador",
    ),
    "apps_files": (
        r"\baplicativo\b",
        r"\bprograma\b",
        r"\bexecut[aá]vel\b",
        r"\batalho\b",
        r"\barquivo\b",
        r"\bpdf\b",
        r"\bpasta\b",
        r"\bdocumento\b",
    ),
    "memory": (
        r"\b(?:listar|liste|mostre|mostrar)\b.*\bmem[oó]ria\b",
        r"\bmem[oó]ria\b.*\b(lembr|salv|esquec|apag)",
        r"\bguarde\b.*\bmem[oó]ria\b",
        r"\blembre(?:-me)?\b.*\bdisso\b",
        r"\besque[cç]a\b.*\bmem[oó]ria\b",
    ),
}


@dataclass(frozen=True)
class TaskRoute:
    status: str
    route: str | None
    capability_id: str | None
    params: dict[str, Any]
    requer_confirmacao_efetiva: bool
    reason_code: str
    reason: str
    clarification_round: int = 0
    max_clarification_rounds: int = 2

    @property
    def should_clarify(self) -> bool:
        return self.status == "unresolved" and self.clarification_round < self.max_clarification_rounds

    @property
    def exhausted(self) -> bool:
        return self.status == "unresolved" and self.clarification_round >= self.max_clarification_rounds


class Router:
    """Roteia o cerebro e seleciona um subconjunto seguro de ferramentas.

    A V43 original continua usando o Fast Brain. A novidade aqui é separar
    tambem o *tool routing*: tarefas claramente reconheciveis recebem apenas
    as ferramentas daquele dominio, enquanto tarefas ambiguas recebem todas as ferramentas disponiveis.
    """

    DEFAULT_BRAIN = "fast"

    def __init__(self) -> None:
        self.last_tool_names: list[str] = []
        self.last_domains: list[str] = []
        self.capability_resolver = CapabilityResolver()
        self.local_decision = LocalDecisionEngine()

    def route_task_spec(self, task_spec: dict[str, Any], *, clarification_round: int = 0) -> TaskRoute:
        """Resolve um TaskSpec v1 sem alterar o roteamento legado da V43."""
        resolution: CapabilityResolution = self.capability_resolver.resolve(
            task_spec,
            clarification_round=clarification_round,
        )
        return TaskRoute(
            status=resolution.status,
            route=resolution.route,
            capability_id=resolution.capability_id,
            params=resolution.params,
            requer_confirmacao_efetiva=resolution.requer_confirmacao_efetiva,
            reason_code=resolution.reason_code,
            reason=resolution.reason,
            clarification_round=resolution.clarification_round,
            max_clarification_rounds=resolution.max_clarification_rounds,
        )

    def decidir_local(self, mensagem: Any) -> DecisionResult:
        """Decide se o pedido tem atalho deterministico. Nao executa nada e nao chama API.

        `choice == "unknown_or_complex"` significa: sem atalho, siga para o modelo
        com as ferramentas de `select_tools()`.
        """
        return self.local_decision.choice(self._extract_text(mensagem))

    def route(
        self,
        mensagem=None,
        *,
        tool_choice=None,
        reasoning_effort="none",
        requested_brain: str | None = None,
    ) -> str:
        if requested_brain in {"fast", "deep"}:
            return requested_brain
        return self.DEFAULT_BRAIN

    @staticmethod
    def _extract_text(entrada: Any) -> str:
        if isinstance(entrada, str):
            return entrada
        if isinstance(entrada, dict):
            partes = []
            for key in ("text", "content", "prompt", "objetivo"):
                value = entrada.get(key)
                if value is not None:
                    partes.append(str(value))
            return " ".join(partes)
        if isinstance(entrada, (list, tuple)):
            partes: list[str] = []
            for item in entrada:
                if isinstance(item, dict):
                    for key in ("text", "content"):
                        value = item.get(key)
                        if value is not None:
                            partes.append(str(value))
                else:
                    partes.append(str(item))
            return " ".join(partes)
        return str(entrada or "")

    def _detectar_dominios(self, mensagem: Any) -> list[str]:
        texto = self._extract_text(mensagem).strip().lower()
        if not texto:
            return []

        encontrados: list[str] = []
        for domain, patterns in DOMAIN_PATTERNS.items():
            if any(re.search(pattern, texto, flags=re.IGNORECASE) for pattern in patterns):
                encontrados.append(domain)

        # Consultar/alterar memoria explicita tem prioridade sobre a palavra
        # "memoria" usada em perguntas de RAM/uso do sistema.
        if any(
            termo in texto
            for termo in ("salvar na memoria", "guardar na memoria", "lembrar", "esquecer da memoria", "apagar memoria")
        ) and "memory" not in encontrados:
            encontrados.append("memory")

        return encontrados

    @staticmethod
    def _acao_visual_pedida(texto: str) -> bool:
        """Detecta manipulacao explicita que pode depender da imagem da tela."""
        patterns = (
            r"\b(?:clique|clica|clicar|selecione|seleciona|selecionar|pressione|pressionar)\b",
            r"\b(?:digite|digitar|escreva|escrever)\b",
            r"\b(?:arraste|arrastar)\b",
            r"\b(?:mova|mover)\b.*\b(?:mouse|cursor|isso|esse|essa)\b",
        )
        return any(re.search(pattern, texto, flags=re.IGNORECASE) for pattern in patterns)

    def select_tool_names(self, mensagem: Any, available_tools: list[dict[str, Any]]) -> list[str]:
        all_names = [item["name"] for item in available_tools]
        texto = self._extract_text(mensagem).strip().lower()
        domains = self._detectar_dominios(mensagem)

        # Sem sinal suficientemente claro: preserva 100% da compatibilidade.
        if not domains:
            self.last_domains = []
            self.last_tool_names = all_names
            return all_names

        selected = set(COMMON_TOOLS)
        spotify_desktop_only = "spotify_desktop" in domains
        for domain in domains:
            if spotify_desktop_only and domain == "browser":
                continue
            selected.update(TOOL_GROUPS[domain])

        # Algumas tarefas atravessam duas fronteiras de forma muito comum.
        # Abrir um aplicativo e mexer na janela normalmente pede ambos.
        if "apps_files" in domains and "browser" not in domains:
            selected.update(TOOL_GROUPS["windows"])
        if "browser" in domains:
            selected.update({"abrir_programa"})  # fallback para navegadores instalados
        if "spotify_desktop" in domains:
            # Spotify playback usa o aplicativo Windows, não o Web Player.
            selected.update(TOOL_GROUPS["spotify_desktop"])
            # Evita carregar ferramentas de browser só porque a palavra Spotify apareceu.
            domains = [d for d in domains if d != "browser"]

        # Quando a rodada realmente depende de enxergar a tela para manipular
        # algo, o modelo precisa receber visão + ações no mesmo subconjunto.
        # Mantemos isso condicionado à presença de uma ação explícita para não
        # expor mouse/UIA em análises puramente visuais.
        if "vision" in domains and self._acao_visual_pedida(texto):
            selected.update(TOOL_GROUPS["input"])
            selected.update(TOOL_GROUPS["uia"])

        ordered = [name for name in all_names if name in selected]

        # Protecao: uma rota especializada precisa manter pelo menos as
        # ferramentas de ancoragem. O sistema (hora/RAM/uptime), por exemplo,
        # corretamente pode ficar com apenas 3 ferramentas.
        if len(ordered) < 2:
            ordered = all_names
            domains = []

        self.last_domains = domains
        self.last_tool_names = ordered
        return ordered

    def select_tools(self, mensagem: Any, available_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = set(self.select_tool_names(mensagem, available_tools))
        return [item for item in available_tools if item["name"] in names]


_ROUTER_PADRAO: Router | None = None


def get_router() -> Router:
    """Instancia unica usada em runtime (orquestrador e atalhos locais compartilham a decisao)."""
    global _ROUTER_PADRAO
    if _ROUTER_PADRAO is None:
        _ROUTER_PADRAO = Router()
    return _ROUTER_PADRAO
