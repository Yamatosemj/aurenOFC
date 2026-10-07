from __future__ import annotations

import builtins
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol


TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class ConfirmationRequest:
    """Pedido de confirmacao produzido pela camada de permissao.
    A requisicao contem apenas a descricao que a interface precisa mostrar.
    Custo: O(1) para construir a estrutura.
    """

    tool_name: str
    action: str
    reason: str
    actions_attempted: int
    max_actions: int
    actions_remaining: int


@dataclass(frozen=True)
class _PendingConfirmation:
    token: str
    created_at: float


class ConfirmationGate:
    """Controla uma unica confirmacao pendente sem expor token ao modelo.
    A interface fornece o token opaco e resolve apenas dentro da janela valida.
    Custo: O(1) por abrir, consultar, resolver ou cancelar uma confirmacao.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = TIMEOUT_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        timeout = float(timeout_seconds)
        if timeout <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero.")
        self._timeout_seconds = timeout
        self._clock = clock or time.monotonic
        self._pending: _PendingConfirmation | None = None
        self._lock = threading.RLock()

    @property
    def timeout_seconds(self) -> float:
        """Retorna a janela maxima da confirmacao desta interface.
        O valor e fixo na instancia e usado para decidir expiracao.
        Custo: O(1).
        """
        return self._timeout_seconds

    def abrir(self, token: str) -> bool:
        """Registra uma confirmacao usando token fornecido pela interface.
        Um segundo pedido enquanto outro ainda estiver valido e recusado.
        Custo: O(1).
        """
        token = str(token or "").strip()
        if not token:
            return False

        agora = self._clock()
        with self._lock:
            if self._esta_expirada(agora):
                self._pending = None

            if self._pending is not None:
                return False

            self._pending = _PendingConfirmation(
                token=token,
                created_at=agora,
            )
            return True

    def resolver(self, token: str, aprovado: bool) -> bool:
        """Resolve a confirmacao somente para o token pendente e ainda valido.
        Token ausente, atrasado ou reutilizado nunca autoriza a acao.
        Custo: O(1).
        """
        agora = self._clock()
        with self._lock:
            pendente = self._pending

            if pendente is None:
                return False

            if agora - pendente.created_at > self._timeout_seconds:
                self._pending = None
                return False

            if str(token or "") != pendente.token:
                return False

            self._pending = None
            return bool(aprovado)

    def cancelar(self, token: str) -> None:
        """Cancela a confirmacao vinculada ao token sem executar nenhuma acao.
        O cancelamento so afeta a confirmacao que pertence a esta interface.
        Custo: O(1).
        """
        with self._lock:
            if self._pending is None:
                return
            if str(token or "") == self._pending.token:
                self._pending = None

    def restante(self, token: str) -> float:
        """Retorna os segundos restantes para o token ainda pendente.
        Token invalido ou confirmacao expirada retorna zero.
        Custo: O(1).
        """
        with self._lock:
            pendente = self._pending
            if pendente is None or str(token or "") != pendente.token:
                return 0.0

            restante = self._timeout_seconds - (self._clock() - pendente.created_at)
            if restante <= 0:
                self._pending = None
                return 0.0
            return restante

    def pendente(self) -> bool:
        """Indica se existe uma confirmacao valida aguardando resposta.
        A consulta tambem remove uma pendencia que ja ultrapassou o timeout.
        Custo: O(1).
        """
        return self.restante(self._pending.token if self._pending else "") > 0

    def _esta_expirada(self, agora: float) -> bool:
        if self._pending is None:
            return False
        return agora - self._pending.created_at > self._timeout_seconds


class ConfirmationChannel(Protocol):
    """Canal responsavel por coletar a decisao do usuario."""

    def confirmar(self, request: ConfirmationRequest) -> bool:
        ...


def _novo_token_de_interface() -> str:
    """Gera um token opaco que permanece somente no canal de interface.
    O token nunca faz parte dos argumentos enviados pelo modelo a uma tool.
    Custo: O(1) para gerar um nonce criptograficamente forte.
    """
    return secrets.token_urlsafe(32)


class TextConfirmationChannel:
    """Canal textual usado pelo Auren fora do modo voz."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
        gate: ConfirmationGate | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._input_fn = input_fn
        self._output_fn = output_fn
        self._gate = gate or ConfirmationGate()
        self._token_factory = token_factory or _novo_token_de_interface

    def confirmar(self, request: ConfirmationRequest) -> bool:
        output = self._output_fn or print
        input_fn = self._input_fn or builtins.input

        token = self._token_factory()
        if not self._gate.abrir(token):
            return False

        try:
            output("\n[PERMISSAO] Auren quer executar uma acao que exige confirmacao.")
            output(f"Acao: {request.action}")
            output(f"Motivo: {request.reason}")
            output(f"Ferramenta: {request.tool_name}")
            output(
                f"Acoes nesta tarefa: {request.actions_attempted}/{request.max_actions} "
                f"| restantes apos esta tentativa: {request.actions_remaining}"
            )

            while self._gate.pendente():
                resposta = input_fn("Autorizar? [s/n]: ").strip().lower()

                if resposta in {"s", "sim", "y", "yes"}:
                    return self._gate.resolver(token, True)

                if resposta in {"n", "nao", "não", "no"}:
                    return self._gate.resolver(token, False)

                output("Responda com 's' ou 'n'.")

            return False
        finally:
            self._gate.cancelar(token)
