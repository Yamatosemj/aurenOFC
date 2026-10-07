from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_profile"
MEMORY_DB_PATH = PROJECT_ROOT / "data" / "memory" / "auren_memory.sqlite3"

AUREN_VERSION = 47
DEFAULT_MODEL = "gpt-5.6-luna"


def _parse_model_ladder(raw: str) -> tuple[str, ...]:
    valores: list[str] = []
    for item in str(raw or "").split(","):
        model = item.strip()
        if model and model not in valores:
            valores.append(model)
    return tuple(valores)


def _parse_timeout(raw: str, default: float = 30.0) -> float:
    try:
        valor = float(str(raw or "").strip())
    except (TypeError, ValueError):
        return default
    return valor if valor > 0 else default


MODEL = os.getenv("AUREN_MODEL", "").strip() or DEFAULT_MODEL
AUREN_MODEL_LADDER = _parse_model_ladder(os.getenv("AUREN_MODEL_LADDER", ""))
MODEL_LADDER = (MODEL,) + tuple(model for model in AUREN_MODEL_LADDER if model != MODEL)

AUREN_REQUEST_TIMEOUT_S = _parse_timeout(
    os.getenv("AUREN_REQUEST_TIMEOUT_S", ""),
    30.0,
)

CACHE_KEY = f"auren-v{AUREN_VERSION}"
ARCHITECTURE_NAME = "V47 ARI NATIVE VISUAL GEOMETRY"

# Response cache seguro para conversas textuais estaveis (nao para estado atual/acoes)
RESPONSE_CACHE_MAX_ITEMS = 50
RESPONSE_CACHE_TTL_SECONDS = 600
