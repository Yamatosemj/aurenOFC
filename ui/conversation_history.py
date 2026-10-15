"""Historico de interface, separado da memoria contextual do Harness.

Texto salvo localmente em SQLite, sem sincronizacao ou criptografia. Nunca
colocar credenciais ou conteudo de conversas em logs do servidor HTTP.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DEFAULT_HISTORY_DB = Path(__file__).resolve().parents[1] / "data" / "ui" / "conversation_history.sqlite3"
PAGE_SIZE = 100
MAX_TEXT = 10000
MAX_SEARCH = 160


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_id(chat_id: str) -> str:
    if not isinstance(chat_id, str) or len(chat_id) != 32 or any(c not in "0123456789abcdef" for c in chat_id):
        raise ValueError("Identificador de conversa invalido.")
    return chat_id


class UiConversationHistory:
    """Historico de mensagens da interface; NAO define o contexto do modelo."""

    def __init__(self, path: str | Path = DEFAULT_HISTORY_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS ui_chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ui_messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL REFERENCES ui_chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','error')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ui_messages_chat ON ui_messages(chat_id, seq);
                CREATE INDEX IF NOT EXISTS ui_chats_updated ON ui_chats(updated_at DESC);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_chat(self) -> str:
        chat_id = uuid4().hex
        now = _now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO ui_chats(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (chat_id, "Nova conversa", now, now),
            )
        return chat_id

    def append(self, chat_id: str, role: str, text: str) -> None:
        chat_id = _validate_id(chat_id)
        if role not in {"user", "assistant", "error"} or not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise ValueError("Mensagem de historico invalida.")
        now = _now()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT title FROM ui_chats WHERE id=?", (chat_id,)).fetchone()
            if row is None:
                raise ValueError("Conversa nao encontrada.")
            if role == "user" and row["title"] == "Nova conversa":
                title = " ".join(text.split())[:72] or "Nova conversa"
                db.execute("UPDATE ui_chats SET title=? WHERE id=?", (title, chat_id))
            db.execute(
                "INSERT INTO ui_messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
                (chat_id, role, text, now),
            )
            db.execute("UPDATE ui_chats SET updated_at=? WHERE id=?", (now, chat_id))

    def list_chats(self, query: str = "", limit: int = 60) -> list[dict]:
        if not isinstance(query, str) or len(query) > MAX_SEARCH:
            raise ValueError("Pesquisa muito longa.")
        limit = max(1, min(100, int(limit)))
        # O caractere de escape faz '%' e '_' serem texto, nunca wildcards.
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        sql = """SELECT c.id,c.title,c.created_at,c.updated_at,
                        (SELECT COUNT(*) FROM ui_messages m WHERE m.chat_id=c.id) AS messages
                 FROM ui_chats c
                 WHERE (? = '' OR c.title LIKE ? ESCAPE '\\'
                    OR EXISTS (SELECT 1 FROM ui_messages m2 WHERE m2.chat_id=c.id
                               AND m2.content LIKE ? ESCAPE '\\'))
                 ORDER BY c.updated_at DESC,c.rowid DESC LIMIT ?"""
        with self._lock, self._connect() as db:
            rows = db.execute(sql, (query.strip(), like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_messages(self, chat_id: str, *, after: int = 0) -> dict:
        chat_id = _validate_id(chat_id)
        if type(after) is not int or after < 0:
            raise ValueError("Cursor invalido.")
        with self._lock, self._connect() as db:
            chat = db.execute(
                "SELECT id,title,created_at,updated_at FROM ui_chats WHERE id=?", (chat_id,)
            ).fetchone()
            if chat is None:
                raise ValueError("Conversa nao encontrada.")
            rows = db.execute(
                "SELECT seq,role,content,created_at FROM ui_messages "
                "WHERE chat_id=? AND seq>? ORDER BY seq ASC LIMIT ?",
                (chat_id, after, PAGE_SIZE + 1),
            ).fetchall()
        more = len(rows) > PAGE_SIZE
        batch = rows[:PAGE_SIZE]
        return {
            "chat": dict(chat),
            "messages": [dict(r) for r in batch],
            "has_more": more,
            "next_after": batch[-1]["seq"] if batch else after,
        }
