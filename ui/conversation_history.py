"""Historico de interface, separado da memoria contextual do Harness.

Texto salvo localmente em SQLite, sem sincronizacao ou criptografia. Nunca
colocar credenciais ou conteudo de conversas em logs do servidor HTTP.
"""
from __future__ import annotations

import sqlite3
import threading
import hashlib
import json
from time import monotonic
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ui.legacy_chat_import import LEGACY_LOG_ROOT, LEGACY_MEMORY_DB, legacy_uuid, read_legacy_sources

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

    def __init__(
        self, path: str | Path = DEFAULT_HISTORY_DB, *,
        legacy_root: Path | None = None,
        memory_db: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._last_legacy_scan = -1e20
        # Bancos temporarios de testes nao devem varrer os logs reais do usuario.
        self._legacy_root = legacy_root if legacy_root is not None else (
            LEGACY_LOG_ROOT if self.path == DEFAULT_HISTORY_DB else None
        )
        self._memory_db = memory_db if memory_db is not None else (
            LEGACY_MEMORY_DB if self.path == DEFAULT_HISTORY_DB else None
        )
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
            columns = {r["name"] for r in db.execute("PRAGMA table_info(ui_chats)")}
            if "source_chat_id" not in columns:
                db.execute("ALTER TABLE ui_chats ADD COLUMN source_chat_id TEXT")
            if "legacy_import" not in columns:
                db.execute("ALTER TABLE ui_chats ADD COLUMN legacy_import INTEGER NOT NULL DEFAULT 0")
            if "legacy_signature" not in columns:
                db.execute("ALTER TABLE ui_chats ADD COLUMN legacy_signature TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ui_chats_source ON ui_chats(source_chat_id)")

    def refresh_legacy(self, *, force: bool = False) -> None:
        """Importa conversas antigas de modo idempotente, sem tocar nas fontes."""
        if self._legacy_root is None or self._memory_db is None:
            return
        with self._lock:
            now = monotonic()
            if not force and now - self._last_legacy_scan < 30:
                return
            # Nao mascarar erro de leitura como historico vazio: importacao nao
            # pode interferir na utilizacao normal da UI.
            try:
                sources = read_legacy_sources(self._legacy_root, self._memory_db)
                with self._connect() as db:
                    known = {
                        r["source_chat_id"]: (r["id"], r["legacy_import"], r["legacy_signature"])
                        for r in db.execute(
                            "SELECT id,source_chat_id,legacy_import,legacy_signature "
                            "FROM ui_chats WHERE source_chat_id IS NOT NULL"
                        )
                    }
                    for source_id, messages in sources.items():
                        if not messages:
                            continue
                        current = known.get(source_id)
                        if current and current[1] == 0:
                            # A conversa foi produzida pela propria UI; nao duplica.
                            continue
                        digest = hashlib.sha256(json.dumps(
                            messages, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")).hexdigest()
                        if current and current[2] == digest:
                            continue
                        chat_id = current[0] if current else legacy_uuid(source_id)
                        title = next((
                            " ".join(content.split())[:72] for role, content, _ in messages if role == "user"
                        ), "Conversa antiga") or "Conversa antiga"
                        created_at = messages[0][2] or _now()
                        updated_at = messages[-1][2] or created_at
                        if current:
                            db.execute(
                                "UPDATE ui_chats SET title=?, updated_at=?, legacy_signature=? WHERE id=?",
                                (title, updated_at, digest, chat_id),
                            )
                            db.execute("DELETE FROM ui_messages WHERE chat_id=?", (chat_id,))
                        else:
                            db.execute(
                                "INSERT INTO ui_chats(id,title,created_at,updated_at,source_chat_id,legacy_import,legacy_signature) "
                                "VALUES(?,?,?,?,?,1,?)",
                                (chat_id, title, created_at, updated_at, source_id, digest),
                            )
                        db.executemany(
                            "INSERT INTO ui_messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
                            [(chat_id, role, content, when or created_at)
                             for role, content, when in messages],
                        )
                self._last_legacy_scan = now
            except (sqlite3.Error, OSError, ValueError):
                # Falha em arquivo legado nao pode bloquear as conversas recentes.
                return

    def bind_harness_chat(self, chat_id: str, source_chat_id: str) -> None:
        """Vincula sessao do Harness a UI; evita importacao duplicada dos logs."""
        chat_id = _validate_id(chat_id)
        from ui.legacy_chat_import import CHAT_NAME
        if not isinstance(source_chat_id, str) or not CHAT_NAME.fullmatch(source_chat_id):
            return
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT id,legacy_import FROM ui_chats WHERE source_chat_id=?",
                (source_chat_id,),
            ).fetchone()
            if existing is not None and existing["id"] != chat_id:
                if not existing["legacy_import"]:
                    return
                db.execute("DELETE FROM ui_chats WHERE id=?", (existing["id"],))
            db.execute(
                "UPDATE ui_chats SET source_chat_id=? WHERE id=? AND legacy_import=0",
                (source_chat_id, chat_id),
            )

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
        self.refresh_legacy()
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
        self.refresh_legacy()
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
