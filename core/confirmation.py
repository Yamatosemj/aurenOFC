from __future__ import annotations

import builtins
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class ConfirmationRequest:
    """Pedido de confirmacao produzido pela camada de permissao."""

    tool_name: str
    action: str
    reason: str
    actions_attempted: int
    max_actions: int
    actions_remaining: int


class ConfirmationChannel(Protocol):
    """Canal responsavel por coletar a decisao do usuario."""

    def confirmar(self, request: ConfirmationRequest) -> bool:
        ...


class TextConfirmationChannel:
    """Canal textual usado pelo Auren fora do modo voz."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._input_fn = input_fn
        self._output_fn = output_fn

    def confirmar(self, request: ConfirmationRequest) -> bool:
        output = self._output_fn or print
        input_fn = self._input_fn or builtins.input

        output("\n[PERMISSAO] Auren quer executar uma acao que exige confirmacao.")
        output(f"Acao: {request.action}")
        output(f"Motivo: {request.reason}")
        output(f"Ferramenta: {request.tool_name}")
        output(
            f"Acoes nesta tarefa: {request.actions_attempted}/{request.max_actions} "
            f"| restantes apos esta tentativa: {request.actions_remaining}"
        )

        while True:
            resposta = input_fn("Autorizar? [s/n]: ").strip().lower()

            if resposta in {"s", "sim", "y", "yes"}:
                return True

            if resposta in {"n", "nao", "não", "no"}:
                return False

            output("Responda com 's' ou 'n'.")
