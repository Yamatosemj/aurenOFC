from __future__ import annotations

from typing import Any, Protocol


class Brain(Protocol):
    name: str

    def create_response(
        self,
        entrada: Any,
        *,
        response_id: str | None = None,
        reasoning_effort: str = "none",
        tool_choice: str | dict | None = None,
    ) -> Any:
        ...
