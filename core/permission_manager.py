from __future__ import annotations

from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any

from core.confirmation import ConfirmationChannel, ConfirmationRequest, TextConfirmationChannel
from core.tool_contracts import capability_for_tool
from tools.file_intelligence import _classify_read_path, _resolve_path


class PermissionLevel(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class PermissionManager:
    """Autoriza ferramentas com base no risco da acao real.

    A protecao e feita fora do modelo: a ferramenta so e executada depois
    que esta camada autoriza a chamada.

    O limite de acoes e reiniciado no inicio de cada tarefa (mensagem do
    usuario). Aciones desconhecidas ficam bloqueadas por seguranca.
    """

    DEFAULT_MAX_ACTIONS = 10

    # Protecoes contra loops de execucao. Essas travas sao adicionais ao
    # limite geral e so entram em jogo quando a execucao apresenta falhas.
    DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
    DEFAULT_MAX_SAME_FAILED_ACTIONS = 2
    DEFAULT_MAX_NO_PROGRESS_REPEATS = 3

    # Politica base por capacidade. O detalhe de uma acao real continua sendo
    # classificado por nivel_da_acao() quando necessario.
    CAPABILITY_POLICY = {
        "memory.write": PermissionLevel.CONFIRM,
        "memory.read": PermissionLevel.AUTO,
        "application.open": PermissionLevel.AUTO,
        "file.search": PermissionLevel.AUTO,
        "file.inspect": PermissionLevel.AUTO,
        "file.read": PermissionLevel.AUTO,
        "windows.process.read": PermissionLevel.AUTO,
        "windows.process.control": PermissionLevel.CONFIRM,
        "windows.window.read": PermissionLevel.AUTO,
        "windows.window.control": PermissionLevel.AUTO,
        "windows.status.read": PermissionLevel.AUTO,
        "windows.screen.read": PermissionLevel.AUTO,
        "windows.clipboard.read": PermissionLevel.AUTO,
        "windows.clipboard.write": PermissionLevel.AUTO,
        "windows.input": PermissionLevel.AUTO,
        "windows.audio.read": PermissionLevel.AUTO,
        "windows.audio.control": PermissionLevel.AUTO,
        "windows.ui.read": PermissionLevel.AUTO,
        "windows.ui.control": PermissionLevel.AUTO,
        "browser.navigation": PermissionLevel.AUTO,
        "browser.read": PermissionLevel.AUTO,
        "browser.input": PermissionLevel.CONFIRM,
        "browser.scroll": PermissionLevel.AUTO,
        "browser.tabs.read": PermissionLevel.AUTO,
        "browser.tabs.control": PermissionLevel.AUTO,
    }

    # O orçamento de ações também é definido por capacidade. Capacidade de
    # leitura não consome orçamento; capacidade de controle sim.
    # Justificativas escritas para toda capacidade mantida em AUTO.
    # O teste de politica exige que esta tabela acompanhe CAPABILITY_POLICY.
    AUTO_CAPABILITY_JUSTIFICATIONS = {
        "memory.read": "Somente consulta memoria; nao altera estado.",
        "application.open": "Abrir um programa e reversivel e nao publica nem envia dados por si so; programas administrativos sao elevados para CONFIRM.",
        "file.search": "Pesquisa nomes/metadados locais sem modificar arquivos.",
        "file.inspect": "Inspecao e somente leitura; caminhos sensiveis ou fora da allowlist sao elevados para CONFIRM/BLOCKED.",
        "file.read": "Leitura e somente leitura; caminhos fora da allowlist exigem CONFIRM.",
        "windows.process.read": "Consulta processos sem alterar execucao.",
        "windows.window.read": "Consulta janelas/geometry sem alterar estado.",
        "windows.window.control": "Somente operacoes de janela reversiveis sao AUTO; fechamento exige CONFIRM.",
        "windows.status.read": "Consulta estado do Windows sem alterar estado.",
        "windows.screen.read": "Captura leitura visual do estado atual, sem efeito externo.",
        "windows.clipboard.read": "Somente leitura do clipboard.",
        "windows.clipboard.write": "Altera estado local do clipboard, mas e reversivel e nao produz efeito externo persistente.",
        "windows.input": "Somente mover o mouse e teclas explicitamente seguras sao AUTO; cliques/arrastes/atalhos destrutivos exigem CONFIRM.",
        "windows.audio.read": "Consulta audio sem alterar estado.",
        "windows.audio.control": "Volume, mudo e midia sao controles locais e reversiveis.",
        "windows.ui.read": "Inspecao UIA e somente leitura.",
        "windows.ui.control": "Somente preenchimento nao sensivel de campos explicitamente seguros e AUTO; demais controles exigem CONFIRM.",
        "browser.navigation": "Navegacao, voltar, avancar e recarregar sao reversiveis e nao submetem formulario por si so.",
        "browser.read": "Somente leitura da pagina atual.",
        "browser.scroll": "Rolar a pagina altera apenas a posicao local de visualizacao.",
        "browser.tabs.read": "Somente leitura da lista de abas.",
        "browser.tabs.control": "Abrir/trocar abas e reversivel; fechar aba exige CONFIRM para evitar perda de estado.",
    }

    REVERSIBLE_WINDOW_CONTROL_TOOLS = frozenset({
        "focar_janela_windows",
        "minimizar_janela_windows",
        "maximizar_janela_windows",
        "mover_janela_windows",
        "redimensionar_janela_windows",
        "restaurar_janela_windows",
    })
    AUTO_WINDOW_INPUT_TOOLS = frozenset({
        "mover_mouse_windows",
    })
    AUTO_BROWSER_NAVIGATION_TOOLS = frozenset({
        "navegar_navegador",
        "voltar_pagina",
        "avancar_pagina",
        "recarregar_pagina",
    })
    AUTO_BROWSER_TAB_CONTROL_TOOLS = frozenset({
        "abrir_nova_aba",
        "trocar_aba",
    })

    COUNTED_CAPABILITIES = {
        "application.open",
        "memory.write",
        "browser.navigation",
        "browser.input",
        "browser.tabs.control",
        "windows.process.control",
        "windows.window.control",
        "windows.input",
        "windows.audio.control",
        "windows.ui.control",
    }

    # Ações cujo sucesso repetido com exatamente os mesmos argumentos pode
    # indicar que a tarefa nao esta avancando. Mantemos o guard restrito
    # para evitar bloquear repetições legitimas de cliques/preenchimentos.
    NO_PROGRESS_GUARD_TOOLS = {
        "navegar_navegador",
    }

    # Alvos explicitamente reconhecidos como consulta/navegacao local.
    # Qualquer alvo fora desta allowlist exige confirmacao.
    SAFE_CLICK_TARGETS = frozenset({
        "pesquisar",
        "buscar",
        "search",
        "resultado",
        "resultados",
        "menu",
        "aba",
        "tab",
        "pagina",
        "visualizar",
        "assistir",
        "video",
        "canal",
        "proximo",
        "anterior",
        "voltar",
        "avancar",
        "expandir",
        "recolher",
        "play",
        "pausar",
        "pause",
        "continuar leitura",
        "ler mais",
    })

    # Campos cuja escrita e explicitamente limitada a consulta/filtro.
    SAFE_FILL_TARGETS = frozenset({
        "pesquisa",
        "pesquisar",
        "busca",
        "buscar",
        "search",
        "url",
        "site",
        "filtro",
        "filter",
        "consulta",
        "query",
        "procurar",
        "procura",
        "searchbox",
    })

    SENSITIVE_FILL_TERMS = {
        "senha",
        "password",
        "passcode",
        "pin",
        "token",
        "codigo de verificacao",
        "código de verificação",
        "verification code",
        "2fa",
        "autenticacao",
        "autenticação",
        "authentication",
        "cpf",
        "cartao",
        "cartão",
        "card",
        "cvv",
        "cvc",
    }

    # Programas que abrem um interpretador/componente administrativo.
    RISKY_PROGRAM_TERMS = {
        "powershell",
        "windows powershell",
        "prompt de comando",
        "command prompt",
        "cmd",
        "terminal",
        "windows terminal",
        "regedit",
        "editor do registro",
        "registry editor",
    }

    SAFE_KEYS = {
        "Tab",
        "Escape",
        "Esc",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "Control+L",
        "Ctrl+L",
        "Control+R",
        "Ctrl+R",
        "F5",
        "Alt+Left",
        "Alt+Right",
    }

    RISKY_KEYS = {
        "Enter",
        "NumpadEnter",
        "Control+Enter",
        "Meta+Enter",
        "Control+W",
        "Ctrl+W",
        "Delete",
        "Backspace",
        "Shift+Delete",
        "Alt+F4",
    }

    def __init__(
        self,
        max_actions: int = DEFAULT_MAX_ACTIONS,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        max_same_failed_actions: int = DEFAULT_MAX_SAME_FAILED_ACTIONS,
        max_no_progress_repeats: int = DEFAULT_MAX_NO_PROGRESS_REPEATS,
        confirmation_channel: ConfirmationChannel | None = None,
    ) -> None:
        if max_actions < 1:
            raise ValueError("max_actions deve ser maior que zero.")
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures deve ser maior que zero.")
        if max_same_failed_actions < 1:
            raise ValueError("max_same_failed_actions deve ser maior que zero.")
        if max_no_progress_repeats < 1:
            raise ValueError("max_no_progress_repeats deve ser maior que zero.")

        self.max_actions = max_actions
        self.max_consecutive_failures = max_consecutive_failures
        self.max_same_failed_actions = max_same_failed_actions
        self.max_no_progress_repeats = max_no_progress_repeats
        self.confirmation_channel = confirmation_channel or TextConfirmationChannel()

        self.actions_attempted = 0
        self.actions_executed = 0
        self.actions_failed = 0

        self.consecutive_failures = 0
        self.last_failed_action_signature: str | None = None
        self.same_failed_action_count = 0

        self.last_successful_action_signature: str | None = None
        self.same_successful_action_count = 0
        self.last_authorized_action_signature: str | None = None
        self.last_authorized_action_tool: str | None = None
        self._fonte_nao_confiavel_pendente: str | None = None

        # A politica base e definida por capacidade, nao por aplicativo ou
        # por cada nome concreto de ferramenta. Classificadores especificos
        # podem elevar o nivel de risco para uma acao individual.
        self.policy: dict[str, PermissionLevel] = dict(self.CAPABILITY_POLICY)

    def registrar_fonte_nao_confiavel(self, nome_ferramenta: str) -> None:
        """Marca que a proxima acao com efeito externo deve exigir confirmacao."""
        self._fonte_nao_confiavel_pendente = str(nome_ferramenta or "").strip() or "desconhecida"

    @property
    def fonte_nao_confiavel_pendente(self) -> str | None:
        return self._fonte_nao_confiavel_pendente

    def iniciar_tarefa(self) -> None:
        self.actions_attempted = 0
        self.actions_executed = 0
        self.actions_failed = 0
        self.consecutive_failures = 0
        self.last_failed_action_signature = None
        self.same_failed_action_count = 0
        self.last_successful_action_signature = None
        self.same_successful_action_count = 0
        self.last_authorized_action_signature = None
        self.last_authorized_action_tool = None
        self._fonte_nao_confiavel_pendente = None

    def conta_para_limite(self, nome_ferramenta: str) -> bool:
        """Indica se a capacidade da tool consome o orcamento de acoes."""
        return self._capability(nome_ferramenta) in self.COUNTED_CAPABILITIES

    def registrar_resultado(self, sucesso: bool, nome_ferramenta: str | None = None, argumentos: dict[str, Any] | None = None) -> None:
        """Registra o resultado da execucao e atualiza as travas anti-loop."""
        if nome_ferramenta is not None and self._capability(nome_ferramenta) not in self.COUNTED_CAPABILITIES:
            return

        if nome_ferramenta is None and argumentos is None and self.last_authorized_action_signature:
            assinatura = self.last_authorized_action_signature
        else:
            assinatura = self._assinatura_acao(
                nome_ferramenta or self.last_authorized_action_tool or "",
                argumentos or {},
            )

        if sucesso:
            self.actions_executed += 1
            self.consecutive_failures = 0
            self.last_failed_action_signature = None
            self.same_failed_action_count = 0

            if assinatura == self.last_successful_action_signature:
                self.same_successful_action_count += 1
            else:
                self.last_successful_action_signature = assinatura
                self.same_successful_action_count = 1
            return

        self.actions_failed += 1
        self.consecutive_failures += 1
        self.last_successful_action_signature = None
        self.same_successful_action_count = 0

        if assinatura == self.last_failed_action_signature:
            self.same_failed_action_count += 1
        else:
            self.last_failed_action_signature = assinatura
            self.same_failed_action_count = 1

    @staticmethod
    def _assinatura_acao(nome_ferramenta: str, argumentos: dict[str, Any]) -> str:
        """Cria uma assinatura estavel sem guardar argumentos sensiveis em claro."""
        try:
            serializado = json.dumps(
                {
                    "ferramenta": nome_ferramenta,
                    "argumentos": argumentos,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        except (TypeError, ValueError, OverflowError):
            serializado = repr((nome_ferramenta, argumentos))

        return hashlib.sha256(serializado.encode("utf-8")).hexdigest()

    def _capability(self, nome_ferramenta: str) -> str:
        try:
            return capability_for_tool(nome_ferramenta)
        except (KeyError, TypeError, ValueError):
            return "unknown"

    def nivel(self, nome_ferramenta: str) -> PermissionLevel:
        """Retorna o nivel base resolvendo a tool pela sua capacidade."""
        capacidade = self._capability(nome_ferramenta)
        return self.policy.get(capacidade, PermissionLevel.BLOCKED)

    def capability(self, nome_ferramenta: str) -> str:
        """Expõe a capacidade canonica associada a uma tool."""
        return self._capability(nome_ferramenta)

    @property
    def acoes_restantes(self) -> int:
        return max(0, self.max_actions - self.actions_attempted)

    def autorizar(
        self,
        nome_ferramenta: str,
        argumentos: dict[str, Any],
    ) -> tuple[bool, str]:
        """Retorna (permitido, motivo) antes da execucao real."""

        capacidade = self._capability(nome_ferramenta)
        conta_para_limite = capacidade in self.COUNTED_CAPABILITIES

        assinatura_atual = self._assinatura_acao(
            nome_ferramenta,
            argumentos,
        )

        if (
            conta_para_limite
            and nome_ferramenta in self.NO_PROGRESS_GUARD_TOOLS
            and assinatura_atual == self.last_successful_action_signature
            and self.same_successful_action_count >= self.max_no_progress_repeats
        ):
            return (
                False,
                (
                    "A mesma acao foi executada repetidamente sem evidência de progresso "
                    f"({self.max_no_progress_repeats} vezes). Tarefa interrompida para evitar um loop."
                ),
            )

        if conta_para_limite and self.consecutive_failures >= self.max_consecutive_failures:
            return (
                False,
                (
                    "Limite de falhas consecutivas atingido nesta tarefa "
                    f"({self.max_consecutive_failures}). Tarefa interrompida."
                ),
            )

        if conta_para_limite and self.same_failed_action_count >= self.max_same_failed_actions:
            return (
                False,
                (
                    "A mesma acao falhou repetidamente nesta tarefa "
                    f"({self.max_same_failed_actions} vezes). Tarefa interrompida "
                    "para evitar um loop."
                ),
            )

        if conta_para_limite and self.actions_attempted >= self.max_actions:
            return (
                False,
                (
                    "Limite de acoes atingido nesta tarefa "
                    f"({self.max_actions}). Tarefa interrompida."
                ),
            )

        if conta_para_limite:
            self.actions_attempted += 1

        nivel, motivo = self.nivel_da_acao(
            nome_ferramenta,
            argumentos,
        )

        if nivel == PermissionLevel.BLOCKED:
            return (
                False,
                motivo,
            )

        if nivel == PermissionLevel.AUTO:
            self.last_authorized_action_signature = assinatura_atual
            self.last_authorized_action_tool = nome_ferramenta
            return True, motivo

        if nivel == PermissionLevel.CONFIRM:
            aprovado = self._pedir_confirmacao(
                nome_ferramenta,
                argumentos,
                motivo,
            )

            if aprovado:
                self.last_authorized_action_signature = assinatura_atual
                self.last_authorized_action_tool = nome_ferramenta
                return True, "Usuario confirmou a acao."

            return False, "Usuario negou a acao."

        return False, "Nivel de permissao desconhecido."

    def nivel_da_acao(
        self,
        nome_ferramenta: str,
        argumentos: dict[str, Any],
    ) -> tuple[PermissionLevel, str]:
        """Classifica a acao real, nao apenas o nome da ferramenta."""

        capacidade = self._capability(nome_ferramenta)
        nivel_base = self.nivel(nome_ferramenta)

        # BLOCKED tem precedencia absoluta, inclusive apos leitura externa.
        if nivel_base == PermissionLevel.BLOCKED:
            return (
                PermissionLevel.BLOCKED,
                (
                    f"A ferramenta '{nome_ferramenta}' "
                    "esta bloqueada pela politica de permissoes."
                ),
            )

        if (
            self._fonte_nao_confiavel_pendente is not None
            and capacidade in self.COUNTED_CAPABILITIES
        ):
            fonte = self._fonte_nao_confiavel_pendente
            return (
                PermissionLevel.CONFIRM,
                (
                    "Esta acao foi solicitada apos a leitura de conteudo nao confiavel "
                    f"(fonte: {fonte}). Conteudo externo nunca e uma instrucao do usuario; "
                    "confirmacao explicita e obrigatoria antes de qualquer acao com efeito externo."
                ),
            )

        if capacidade in {"file.read", "file.inspect"}:
            path = _resolve_path(str(argumentos.get("caminho", "")))
            path_policy = _classify_read_path(path)
            if path_policy.status == "blocked":
                return PermissionLevel.BLOCKED, path_policy.motivo
            if path_policy.status == "confirm":
                return PermissionLevel.CONFIRM, path_policy.motivo
            return PermissionLevel.AUTO, path_policy.motivo

        if capacidade == "windows.window.control":
            if nome_ferramenta in self.REVERSIBLE_WINDOW_CONTROL_TOOLS:
                return (
                    PermissionLevel.AUTO,
                    "Controle de janela limitado a operacao reversivel; fechamento fica explicitamente fora da allowlist.",
                )
            return (
                PermissionLevel.CONFIRM,
                "Controle de janela fora da allowlist de operacoes reversiveis; confirmacao obrigatoria.",
            )

        if capacidade == "windows.input":
            if nome_ferramenta == "pressionar_tecla_windows":
                return self._classificar_tecla(argumentos)
            if nome_ferramenta in self.AUTO_WINDOW_INPUT_TOOLS:
                return (
                    PermissionLevel.AUTO,
                    "Movimento de cursor nao altera estado externo e pode ser desfeito por novo movimento.",
                )
            return (
                PermissionLevel.CONFIRM,
                "Entrada global fora da allowlist segura; clique/arraste e atalhos potencialmente acionaveis exigem confirmacao.",
            )

        if capacidade == "windows.ui.control":
            if nome_ferramenta == "preencher_elemento_windows":
                return self._classificar_preenchimento(argumentos)
            return (
                PermissionLevel.CONFIRM,
                "Controle UI Automation fora da allowlist de escrita nao acionavel; clique, toggle e selecao exigem confirmacao.",
            )

        if capacidade == "browser.navigation":
            if nome_ferramenta in self.AUTO_BROWSER_NAVIGATION_TOOLS:
                return (
                    PermissionLevel.AUTO,
                    "Acao limitada a navegacao reversivel do navegador; nao submete formularios por si so.",
                )
            return (
                PermissionLevel.CONFIRM,
                "Ferramenta de navegacao fora da allowlist explicita; confirmacao obrigatoria.",
            )

        if capacidade == "browser.tabs.control":
            if nome_ferramenta in self.AUTO_BROWSER_TAB_CONTROL_TOOLS:
                return (
                    PermissionLevel.AUTO,
                    "Abrir ou trocar aba e reversivel e nao fecha nem apaga estado.",
                )
            return (
                PermissionLevel.CONFIRM,
                "Controle de abas fora da allowlist segura; fechamento exige confirmacao.",
            )

        if capacidade in {"browser.input", "windows.ui.control"} and nome_ferramenta in {"clicar_elemento", "clicar_elemento_windows", "alternar_elemento_windows", "selecionar_elemento_windows"}:
            return self._classificar_clique({"alvo": argumentos.get("alvo", "")})

        if capacidade == "browser.input" and nome_ferramenta in {"preencher_elemento"}:
            return self._classificar_preenchimento(argumentos)

        if nome_ferramenta == "pressionar_tecla":
            return self._classificar_tecla(argumentos)

        if capacidade == "windows.process.control":
            return (
                PermissionLevel.CONFIRM,
                "Encerrar um processo pode perder trabalho ou fechar um programa sem salvar.",
            )

        if capacidade == "application.open":
            return self._classificar_programa(argumentos)

        if nivel_base == PermissionLevel.AUTO:
            return (
                PermissionLevel.AUTO,
                "Acao classificada como automatica: nao produz alteracao externa relevante.",
            )

        return (
            nivel_base,
            "Acao requer confirmacao pela politica base da ferramenta.",
        )

    def _classificar_clique(
        self,
        argumentos: dict[str, Any],
    ) -> tuple[PermissionLevel, str]:
        alvo = self._normalizar_texto(
            argumentos.get("alvo", "")
        )

        if not alvo:
            return (
                PermissionLevel.CONFIRM,
                "Clique sem um alvo textual claro: confirmacao obrigatoria.",
            )

        if alvo in self.SAFE_CLICK_TARGETS:
            return (
                PermissionLevel.AUTO,
                "Clique corresponde a um alvo explicitamente autorizado para consulta/navegacao.",
            )

        return (
            PermissionLevel.CONFIRM,
            "Alvo de clique fora da allowlist segura; confirmacao obrigatoria.",
        )

    def _classificar_preenchimento(
        self,
        argumentos: dict[str, Any],
    ) -> tuple[PermissionLevel, str]:
        alvo = self._normalizar_texto(
            argumentos.get("alvo", "")
        )

        if bool(argumentos.get("_uia_protegido")):
            return (
                PermissionLevel.CONFIRM,
                "O controle UI Automation resolvido e protegido por IsPassword; confirmacao obrigatoria.",
            )

        if self._contem_termo(alvo, self.SENSITIVE_FILL_TERMS):
            return (
                PermissionLevel.CONFIRM,
                "Campo aparenta conter dado sensivel, senha ou credencial.",
            )

        if self._normalizar_texto(alvo) in {self._normalizar_texto(item) for item in self.SAFE_FILL_TARGETS}:
            return (
                PermissionLevel.AUTO,
                "Campo corresponde a um alvo explicitamente autorizado para consulta/filtro.",
            )

        return (
            PermissionLevel.CONFIRM,
            "Campo fora da allowlist explicita de consulta/filtro; confirmacao obrigatoria antes de escrever.",
        )

    def _classificar_tecla(
        self,
        argumentos: dict[str, Any],
    ) -> tuple[PermissionLevel, str]:
        tecla = str(
            argumentos.get("tecla", "")
        ).strip()
        tecla_normalizada = self._normalizar_texto(tecla)
        safe_keys = {self._normalizar_texto(item) for item in self.SAFE_KEYS}
        risky_keys = {self._normalizar_texto(item) for item in self.RISKY_KEYS}

        if tecla_normalizada in safe_keys:
            return (
                PermissionLevel.AUTO,
                "Tecla classificada como navegacao/controle local seguro.",
            )

        if tecla_normalizada in risky_keys:
            return (
                PermissionLevel.CONFIRM,
                "Tecla pode submeter, apagar ou fechar algo dependendo do contexto.",
            )

        return (
            PermissionLevel.CONFIRM,
            "Tecla desconhecida ou potencialmente acionavel: confirmacao obrigatoria.",
        )

    def _classificar_programa(
        self,
        argumentos: dict[str, Any],
    ) -> tuple[PermissionLevel, str]:
        programa = self._normalizar_texto(
            argumentos.get("programa", "")
        )

        if self._contem_termo(programa, self.RISKY_PROGRAM_TERMS):
            return (
                PermissionLevel.CONFIRM,
                "Programa pode executar comandos ou alterar configuracoes do sistema.",
            )

        return (
            PermissionLevel.AUTO,
            "Abertura de programa classificada como automatica.",
        )

    def _pedir_confirmacao(
        self,
        nome_ferramenta: str,
        argumentos: dict[str, Any],
        motivo: str,
    ) -> bool:
        request = ConfirmationRequest(
            tool_name=nome_ferramenta,
            action=self._descrever_acao(nome_ferramenta, argumentos),
            reason=motivo,
            actions_attempted=self.actions_attempted,
            max_actions=self.max_actions,
            actions_remaining=self.acoes_restantes,
        )
        return bool(self.confirmation_channel.confirmar(request))

    def _descrever_acao(
        self,
        nome_ferramenta: str,
        argumentos: dict[str, Any],
    ) -> str:
        capacidade = self._capability(nome_ferramenta)

        if nome_ferramenta == "clicar_elemento":
            alvo = argumentos.get("alvo", "")
            indice = argumentos.get("indice", 1)
            return f"clicar em {alvo!r} (ocorrencia {indice})"

        if capacidade in {"browser.input", "windows.ui.control"} and nome_ferramenta in {"preencher_elemento", "preencher_elemento_windows"}:
            alvo = argumentos.get("alvo", "")
            texto = self._mascarar_valor(
                argumentos.get("texto", "")
            )
            protegido = bool(argumentos.get("_uia_protegido"))
            prefixo = "preencher controle protegido " if protegido else "preencher "
            return f"{prefixo}{alvo!r} com {texto!r}"

        if nome_ferramenta == "arrastar_mouse_windows":
            origem = (argumentos.get("x_inicial"), argumentos.get("y_inicial"))
            destino = (argumentos.get("x_final"), argumentos.get("y_final"))
            return f"arrastar de {origem} para {destino} ({argumentos.get('descricao', '')})"

        if nome_ferramenta == "pressionar_tecla":
            return f"pressionar a tecla {argumentos.get('tecla', '')!r}"

        if capacidade == "application.open":
            return f"abrir o programa {argumentos.get('programa', '')!r}"

        if capacidade == "memory.write":
            if nome_ferramenta == "salvar_memoria_persistente":
                chave = argumentos.get("chave", "")
                return f"salvar memoria persistente para a chave {chave!r}"
            if nome_ferramenta == "esquecer_memoria_persistente":
                chave = argumentos.get("chave", "")
                return f"esquecer a memoria persistente {chave!r}"
            return "alterar memoria persistente"

        return self._formatar_argumentos(argumentos)

    def _mascarar_valor(self, valor: Any) -> str:
        texto = str(valor)
        if len(texto) <= 2:
            return "[REDACTADO]"
        return f"{texto[0]}{'*' * min(8, len(texto) - 2)}{texto[-1]}"

    @staticmethod
    def _formatar_argumentos(
        argumentos: dict[str, Any],
    ) -> str:
        partes: list[str] = []

        for chave, valor in argumentos.items():
            chave_normalizada = str(chave).lower()

            sensivel = any(
                termo in chave_normalizada
                for termo in (
                    "senha",
                    "password",
                    "token",
                    "secret",
                    "codigo",
                    "code",
                    "pin",
                    "cvv",
                    "cvc",
                    "texto",
                    "conteudo",
                    "conteúdo",
                    "clipboard",
                )
            )

            if sensivel:
                valor_exibido = "[REDACTADO]"
            else:
                valor_exibido = repr(valor)

            partes.append(
                f"{chave}={valor_exibido}"
            )

        return ", ".join(partes) if partes else "sem argumentos"

    @staticmethod
    def _normalizar_texto(texto: Any) -> str:
        bruto = unicodedata.normalize("NFKD", str(texto).strip().lower())
        sem_acentos = "".join(
            caractere
            for caractere in bruto
            if not unicodedata.combining(caractere)
        )
        return " ".join(sem_acentos.split())

    @classmethod
    def _contem_termo(
        cls,
        texto: str,
        termos: set[str],
    ) -> bool:
        texto_normalizado = cls._normalizar_texto(texto)

        for termo in termos:
            termo_normalizado = cls._normalizar_texto(termo)
            if not termo_normalizado:
                continue

            padrao = rf"(?<!\w){re.escape(termo_normalizado)}(?!\w)"
            if re.search(padrao, texto_normalizado):
                return True

        return False
