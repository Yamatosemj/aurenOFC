"""LLM response cache transplantado do Ari.

Mantido isolado do Core para que o Auren possa usar a capacidade sem adotar
as dependências de configuração específicas do Ari.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Optional

DEFAULT_RESPONSE_CACHE_MAX_ITEMS = 50
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 600


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return coerced if coerced > 0 else default


class ResponseCache:
    """Cache LRU em memória com TTL, conforme o componente do Ari."""

    def __init__(
        self,
        max_items: int = DEFAULT_RESPONSE_CACHE_MAX_ITEMS,
        ttl_seconds: int = DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
    ):
        self.max_items = _coerce_positive_int(max_items, DEFAULT_RESPONSE_CACHE_MAX_ITEMS)
        self.ttl_seconds = _coerce_positive_int(ttl_seconds, DEFAULT_RESPONSE_CACHE_TTL_SECONDS)
        self._store: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    @classmethod
    def from_config(cls) -> "ResponseCache":
        """Carrega configuração do Auren quando disponível; usa defaults caso contrário."""
        try:
            from config import RESPONSE_CACHE_MAX_ITEMS, RESPONSE_CACHE_TTL_SECONDS
            return cls(RESPONSE_CACHE_MAX_ITEMS, RESPONSE_CACHE_TTL_SECONDS)
        except Exception:
            return cls()

    def get(self, cache_key: str) -> Optional[str]:
        with self._lock:
            item = self._store.get(cache_key)
            if not item:
                self.misses += 1
                return None
            saved_at, response = item
            if time.time() - saved_at > self.ttl_seconds:
                self._store.pop(cache_key, None)
                self.misses += 1
                return None
            self._store.move_to_end(cache_key)
            self.hits += 1
            return response

    def set(self, cache_key: str, response: str) -> None:
        with self._lock:
            self._store[cache_key] = (time.time(), response)
            self._store.move_to_end(cache_key)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "itens": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
            }


def build_response_cache_key(
    message: str,
    *,
    provider: str,
    model: str,
    system_prompt: str,
    personality: str,
    scenario: str,
    history_instruction: str,
    include_context: bool,
) -> str:
    payload = {
        "message": message,
        "provider": provider,
        "model": model,
        "system_prompt": system_prompt,
        "personality": personality,
        "scenario": scenario,
        "history_instruction": history_instruction,
        "include_context": include_context,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
