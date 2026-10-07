from __future__ import annotations

import json
from typing import Any

from core.tool_result import ToolResult
from memory.store import PersistentMemoryStore


def _resultado_memoria(resultado: dict[str, Any], tool_name: str) -> ToolResult:
    mensagem = json.dumps(resultado, ensure_ascii=False, separators=(",", ":"))
    if bool(resultado.get("ok")):
        return ToolResult.success(mensagem, tool_name=tool_name)
    return ToolResult.failure(
        mensagem,
        error_code="memory_error",
        tool_name=tool_name,
    )


def salvar_memoria_persistente(
    store: PersistentMemoryStore,
    chave: str = "",
    valor: str = "",
    categoria: str = "geral",
) -> ToolResult:
    return _resultado_memoria(
        store.salvar(chave, valor, categoria),
        "salvar_memoria_persistente",
    )


def consultar_memoria_persistente(
    store: PersistentMemoryStore,
    consulta: str = "",
    limite: int = 5,
) -> ToolResult:
    return _resultado_memoria(
        store.consultar(consulta, limite),
        "consultar_memoria_persistente",
    )


def esquecer_memoria_persistente(
    store: PersistentMemoryStore,
    chave: str = "",
) -> ToolResult:
    return _resultado_memoria(
        store.esquecer(chave),
        "esquecer_memoria_persistente",
    )
