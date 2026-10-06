from __future__ import annotations

from typing import Any


class DeepBrain:
    """Ponto de extensao para tarefas de planejamento mais profundas."""

    name = "deep"

    def __init__(self, provider) -> None:
        self.provider = provider

    def create_response(
        self,
        entrada: Any,
        *,
        response_id: str | None = None,
        reasoning_effort: str = "none",
        tool_choice: str | dict | None = None,
        tools=None,
    ) -> Any:
        return self.provider.create_response(
            entrada,
            response_id=response_id,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            tools=tools,
        )
