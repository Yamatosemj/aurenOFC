from __future__ import annotations

import json
from typing import Any

from memory.store import PersistentMemoryStore


def salvar_memoria_persistente(store: PersistentMemoryStore, chave: str = "", valor: str = "", categoria: str = "geral") -> str:
    return json.dumps(store.salvar(chave, valor, categoria), ensure_ascii=False, separators=(",", ":"))


def consultar_memoria_persistente(store: PersistentMemoryStore, consulta: str = "", limite: int = 5) -> str:
    return json.dumps(store.consultar(consulta, limite), ensure_ascii=False, separators=(",", ":"))


def esquecer_memoria_persistente(store: PersistentMemoryStore, chave: str = "") -> str:
    return json.dumps(store.esquecer(chave), ensure_ascii=False, separators=(",", ":"))
