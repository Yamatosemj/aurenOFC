from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_profile"
MEMORY_DB_PATH = PROJECT_ROOT / "data" / "memory" / "auren_memory.sqlite3"

AUREN_VERSION = 49
DEFAULT_MODEL = "gpt-5.6-luna"
MODEL = os.getenv("AUREN_MODEL", "").strip() or DEFAULT_MODEL
CACHE_KEY = f"auren-v{AUREN_VERSION}"
ARCHITECTURE_NAME = "V49 WINDOWS REMINDERS"

# Response cache seguro para conversas textuais estaveis (nao para estado atual/acoes)
RESPONSE_CACHE_MAX_ITEMS = 50
RESPONSE_CACHE_TTL_SECONDS = 600
