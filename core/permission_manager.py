from __future__ import annotations

from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any

from core.tool_contracts import capability_for_tool


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

    # Clics que normalmente so navegam/consultam o site e nao causam
    # uma mudanca externa relevante.
    SAFE_CLICK_TERMS = {
        "pesquisar",
        "pesquisa",
        "buscar",
        "busca",
        "search",
        "abrir",
        "aberto",
        "ver",
        "visualizar",
        "assistir",
        "video",
        "vídeo",
        "canal",
        "resultado",
        "resultados",
        "menu",
        "aba",
        "tab",
        "pagina",
        "página",
        "proximo",
        "próximo",
        "anterior",
        "voltar",
        "avancar",
        "avançar",
        "mais",
        "menos",
        "detalhes",
        "expandir",
        "recolher",
        "play",
        "pausar",
        "pause",
        "fechar",
        "continuar leitura",
        "ler mais",
    }

    # Clics que podem publicar, enviar, alterar conta, pagar ou destruir algo.
    RISKY_CLICK_TERMS = {
        "enviar",
        "send",
        "enviar mensagem",
        "send message",
        "publicar",
        "publish",
        "postar",
        "post",
        "comentar",
        "comentar e enviar",
        "comprar",
        "buy",
        "checkout",
        "finalizar compra",
        "finalizar pedido",
        "pagar",
        "pay",
        "assinar",
        "assinar plano",
        "subscribe",
        "inscrever-se",
        "inscrever se",
        "confirmar compra",
        "confirmar pedido",
        "excluir",
        "apagar",
        "deletar",
        "delete",
        "remover",
        "remove",
        "cancelar assinatura",
        "cancel subscription",
        "cancelar conta",
        "excluir conta",
        "delete account",
        "sair da conta",
        "logout",
        "log out",
        "entrar",
        "login",
        "log in",
        "sign in",
        "continuar com google",
        "continuar com microsoft",
        "permitir",
        "allow",
        "autorizar",
        "authorize",
        "conceder acesso",
        "grant access",
        "seguir",
        "follow",
        "bloquear",
        "block",
        "denunciar",
        "report",
        "confirmar",
        "confirm",
        "ok",
        "aceitar",
        "accept",
        "aplicar",
        "apply",
        "salvar",
        "save",
        "instalar",
        "install",
        "executar",
        "run",
        "ativar",
        "enable",
        "desativar",
        "disable",
    }

    SAFE_FILL_TERMS = {
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
    }

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

        # A politica base e definida por capacidade, nao por aplicativo ou
        # por cada nome concreto de ferramenta. Classificadores especificos
        # podem elevar o nivel de risco para uma acao individual.
        self.policy: dict[str, PermissionLevel] = dict(self.CAPABILITY_POLICY)

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
        except Exception:
            serializado = repr((nome_ferramenta, argumentos))

        return hashlib.sha256(serializado.encode("utf-8")).hexdigest()

    def _capability(self, nome_ferramenta: str) -> str:
        try:
            return capability_for_tool(nome_ferramenta)
        except Exception:
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

        if nivel_base == PermissionLevel.BLOCKED:
            return (
                PermissionLevel.BLOCKED,
                (
                    f"A ferramenta '{nome_ferramenta}' "
                    "esta bloqueada pela politica de permissoes."
                ),
            )

        if capacidade in {"browser.input", "windows.ui.control"} and nome_ferramenta in {"clicar_elemento", "clicar_elemento_windows", "alternar_elemento_windows", "selecionar_elemento_windows"}:
            return self._classificar_clique({"alvo": argumentos.get("alvo", "")})

        if capacidade in {"browser.input", "windows.ui.control"} and nome_ferramenta in {"preencher_elemento", "preencher_elemento_windows"}:
            return self._classificar_preenchimento(argumentos)

        if nome_ferramenta == "pressionar_tecla":
            return self._classificar_tecla(argumentos)

        if nome_ferramenta == "pressionar_tecla_windows":
            return self._classificar_tecla(argumentos)

        if capacidade == "windows.input" and nome_ferramenta == "clicar_mouse_windows":
            return (
                PermissionLevel.CONFIRM,
                "Clique global por coordenada exige confirmacao; a descricao do alvo fornecida pelo modelo nao e prova de seguranca.",
            )

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

        if self._contem_termo(alvo, self.RISKY_CLICK_TERMS):
            return (
                PermissionLevel.CONFIRM,
                (
                    "Clique pode enviar/publicar, alterar conta, "
                    "autorizar acesso, comprar, cancelar ou excluir algo."
                ),
            )

        if self._contem_termo(alvo, self.SAFE_CLICK_TERMS):
            return (
                PermissionLevel.AUTO,
                "Clique classificado como navegacao/consulta segura.",
            )

        # Clique sem indicios de efeito externo perigoso.
        # Acoes como enviar, comprar, excluir, autorizar etc. continuam
        # exigindo confirmacao acima. Links normais e navegacao ficam automaticos.
        return (
            PermissionLevel.AUTO,
            "Clique classificado como navegacao/consulta por nao conter sinais de acao externa perigosa.",
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

        if self._contem_termo(alvo, self.SAFE_FILL_TERMS):
            return (
                PermissionLevel.AUTO,
                "Preenchimento classificado como pesquisa/filtro/navegacao.",
            )

        return (
            PermissionLevel.AUTO,
            "Preenchimento sem dado sensivel; nao envia nem publica nada por si so.",
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
        print("\n[PERMISSAO] Auren quer executar uma acao que exige confirmacao.")
        print(f"Acao: {self._descrever_acao(nome_ferramenta, argumentos)}")
        print(f"Motivo: {motivo}")
        print(f"Ferramenta: {nome_ferramenta}")
        print(
            f"Acoes nesta tarefa: {self.actions_attempted}/{self.max_actions} "
            f"| restantes apos esta tentativa: {self.acoes_restantes}"
        )

        while True:
            resposta = input("Autorizar? [s/n]: ").strip().lower()

            if resposta in {"s", "sim", "y", "yes"}:
                return True

            if resposta in {"n", "nao", "não", "no"}:
                return False

            print("Responda com 's' ou 'n'.")

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
