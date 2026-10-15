"""Importacao somente de leitura dos chats antigos (sem mudar o logger).

A fonte de mensagens conversacionais e o banco de memoria; log tecnico e
usado exclusivamente para identificar chats e, quando faltar memoria, recuperar
TASK_START/objetivo. Nunca usar MODEL_ROUND_RESPONSE como resposta do assistente:
pode ser pensamento intermediario, texto parcial ou uma rodada de ferramenta.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from uuid import UUID, uuid5

LEGACY_LOG_ROOT = Path(__file__).resolve().parents[1] / "logs" / "chats"
LEGACY_MEMORY_DB = Path(__file__).resolve().parents[1] / "data" / "memory" / "auren_memory.sqlite3"
LEGACY_ID_NAMESPACE = UUID("2f618586-c28b-4fbf-9e04-5775099393ce")
CHAT_NAME = re.compile(r"^chat-\d{8}-\d{6}-\d{6}$")
EVENT_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[^\]]*)\] ([A-Z][A-Z0-9_]*)$")
FIELD_LINE = re.compile(r"^  ([a-zA-Z_][a-zA-Z0-9_]*): (.+)$")
MAX_SOURCE_FILE = 16 * 1024 * 1024
MAX_MESSAGE = 10000
MAX_LOG_EVENTS = 30000


def legacy_uuid(source_chat_id: str) -> str:
    return uuid5(LEGACY_ID_NAMESPACE, source_chat_id).hex


def _memory_turns(path: Path) -> dict[str, list[tuple[str, str, str]]]:
    """Abre o SQLite original SOMENTE com mode=ro, sem criar/modificar tabelas."""
    if not path.is_file() or path.is_symlink():
        return {}
    uri = path.resolve().as_uri() + "?mode=ro"
    groups: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    try:
        with sqlite3.connect(uri, uri=True, timeout=2) as db:
            rows = db.execute(
                "SELECT chat_id,papel,conteudo,criado_em FROM conversas "
                "WHERE papel IN ('user','assistant') ORDER BY id ASC"
            )
            for cid, role, text, created in rows:
                if isinstance(cid, str) and CHAT_NAME.fullmatch(cid) and isinstance(text, str) and text.strip():
                    groups[cid].append((role, text[:MAX_MESSAGE], str(created or "")))
    except (sqlite3.Error, OSError):
        return {}
    return dict(groups)


def _decode_field(raw: str) -> str | None:
    # Os valores usam JSON compacto; ignorar JSON truncado/garbled, sem adivinhar.
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _log_turns(path: Path) -> list[tuple[str, str, str]]:
    """Somente eventos TASK_START/objetivo sao mensagens do usuario."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE_FILE:
        return []
    result: list[tuple[str, str, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as source:
            event = ""
            timestamp = ""
            events_seen = 0
            for line in source:
                head = EVENT_LINE.fullmatch(line.rstrip("\r\n"))
                if head:
                    timestamp, event = head.groups()
                    events_seen += 1
                    if events_seen > MAX_LOG_EVENTS:
                        break
                    continue
                if event != "TASK_START":
                    continue
                field = FIELD_LINE.fullmatch(line.rstrip("\r\n"))
                if field and field.group(1) == "objetivo":
                    message = _decode_field(field.group(2))
                    if message and message.strip():
                        result.append(("user", message[:MAX_MESSAGE], timestamp))
                    event = ""
    except OSError:
        return []
    return result


def read_legacy_sources(
    log_root: Path = LEGACY_LOG_ROOT,
    memory_db: Path = LEGACY_MEMORY_DB,
) -> dict[str, list[tuple[str, str, str]]]:
    """Nenhuma escrita em logs ou memoria; importar dados como texto de chat."""
    memory = _memory_turns(memory_db)
    result = dict(memory)
    if not log_root.is_dir() or log_root.is_symlink():
        return result
    base = log_root.resolve()
    for log_path in log_root.glob("chat-*/chat/chat.log"):
        cid = log_path.parent.parent.name
        if not CHAT_NAME.fullmatch(cid) or cid in memory:
            # A memoria do Harness preserva os turnos finais; log contem etapas.
            continue
        try:
            if not log_path.resolve().is_relative_to(base):
                continue
            fallback = _log_turns(log_path)
            if fallback:
                result[cid] = fallback
        except OSError:
            continue
    return result
