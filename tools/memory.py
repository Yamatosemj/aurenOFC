from __future__ import annotations

import json
from typing import Any

from memory.store import PersistentMemoryStore
from core.tool_result import ToolResult, from_legacy


def salvar_memoria_persistente(store: PersistentMemoryStore, chave: str = "", valor: str = "", categoria: str = "geral") -> ToolResult:
    return from_legacy(store.salvar(chave, valor, categoria), tool_name="salvar_memoria_persistente")


def consultar_memoria_persistente(store: PersistentMemoryStore, consulta: str = "", limite: int = 5) -> str:
    return json.dumps(store.consultar(consulta, limite), ensure_ascii=False, separators=(",", ":"))


def esquecer_memoria_persistente(store: PersistentMemoryStore, chave: str = "") -> ToolResult:
    return from_legacy(store.esquecer(chave), tool_name="esquecer_memoria_persistente")
