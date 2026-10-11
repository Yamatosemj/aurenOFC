"""Lembretes locais persistentes. Relogio e armazenamento nao chamam IA."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re
import sqlite3
from threading import Lock, RLock
from typing import Callable

from core.tool_result import ToolResult


DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "reminders" / "auren_reminders.sqlite3"
VALID_STATES = {"pendente", "notificado", "concluido", "cancelado"}


def interpretar_quando(quando: str, agora: datetime) -> datetime:
    """Suporta horario local explicito, hoje/amanha, ISO e intervalos curtos."""
    value = str(quando or "").strip().casefold()
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise ValueError("Informe quando avisar, por exemplo 'hoje 15:00' ou 'em 10 minutos'.")
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("Relogio local sem fuso horario.")

    match = re.fullmatch(r"(?:daqui a|em) (\d{1,5}) (minuto|minutos|hora|horas)", value)
    if match:
        n = int(match.group(1))
        if n < 1:
            raise ValueError("Intervalo deve ser maior que zero.")
        return agora + timedelta(minutes=n * (60 if match.group(2).startswith("hora") else 1))

    match = re.fullmatch(r"(hoje|amanh[aã])(?:\s+[aà]s?)?\s+(\d{1,2})(?:[:h](\d{2}))?h?", value)
    if match:
        hour, minute = int(match.group(2)), int(match.group(3) or 0)
        if hour > 23 or minute > 59:
            raise ValueError("Horario invalido.")
        date = agora.date() + timedelta(days=int(match.group(1) != "hoje"))
        return datetime(date.year, date.month, date.day, hour, minute, tzinfo=agora.tzinfo)

    try:
        parsed = datetime.fromisoformat(value.replace("z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Horario invalido. Use 'hoje 15:00', 'em 10 minutos' ou ISO 8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=agora.tzinfo)
    return parsed.astimezone(agora.tzinfo)


class ReminderStore:
    """SQLite com atualizacoes atomicas para evitar alertas repetidos."""

    def __init__(self, path: str | Path | None = None, *, clock: Callable[[], datetime] | None = None):
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS lembretes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                texto TEXT NOT NULL,
                horario TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_lembretes_pendentes ON lembretes(status, horario)")

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Relogio deve ter fuso horario.")
        return now

    @staticmethod
    def _record(row) -> dict:
        return {"id": row["id"], "texto": row["texto"], "horario": row["horario"], "status": row["status"]}

    def criar(self, texto: str, quando: str) -> dict:
        texto = str(texto or "").strip()
        if not texto or len(texto) > 300:
            raise ValueError("O lembrete precisa ter texto entre 1 e 300 caracteres.")
        now = self._now()
        future = interpretar_quando(quando, now)
        if future <= now:
            raise ValueError("O horario ja passou. Informe um horario futuro.")
        if future > now + timedelta(days=365 * 5):
            raise ValueError("O horario deve estar dentro dos proximos cinco anos.")
        stamp = now.isoformat(timespec="seconds")
        due = future.isoformat(timespec="seconds")
        with self._lock, self._connect() as con:
            cursor = con.execute(
                "INSERT INTO lembretes(texto, horario, criado_em, atualizado_em) VALUES (?,?,?,?)",
                (texto, due, stamp, stamp),
            )
            return {"id": cursor.lastrowid, "texto": texto, "horario": due, "status": "pendente"}

    def listar(self, *, status: str = "ativos", limite: int = 20) -> list[dict]:
        if status not in {"ativos", "todos", *VALID_STATES}:
            raise ValueError("Filtro de lembrete invalido.")
        if not 1 <= limite <= 50:
            raise ValueError("Limite deve estar entre 1 e 50.")
        where = {
            "ativos": "status IN ('pendente', 'notificado')",
            "todos": "1=1",
        }.get(status, "status = ?")
        params = () if status in ("ativos", "todos") else (status,)
        with self._lock, self._connect() as con:
            rows = con.execute(
                f"SELECT id, texto, horario, status FROM lembretes WHERE {where} "
                "ORDER BY horario ASC LIMIT ?",
                (*params, limite),
            ).fetchall()
        return [self._record(row) for row in rows]

    def alterar(self, reminder_id: int, action: str, minutos: int = 10) -> dict:
        if type(reminder_id) is not int or reminder_id < 1:
            raise ValueError("ID de lembrete invalido.")
        if action not in {"concluir", "cancelar", "adiar"}:
            raise ValueError("Acao invalida.")
        now = self._now()
        with self._lock, self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM lembretes WHERE id=?", (reminder_id,)).fetchone()
            if row is None:
                raise ValueError("Lembrete nao encontrado.")
            if row["status"] in ("concluido", "cancelado"):
                raise ValueError("Lembrete ja encerrado.")
            if action == "adiar":
                if not 1 <= minutos <= 10080:
                    raise ValueError("Adiamento deve ser de 1 a 10080 minutos.")
                due = (now + timedelta(minutes=minutos)).isoformat(timespec="seconds")
                status = "pendente"
            else:
                due = row["horario"]
                status = "concluido" if action == "concluir" else "cancelado"
            con.execute(
                "UPDATE lembretes SET horario=?, status=?, atualizado_em=? WHERE id=?",
                (due, status, now.isoformat(timespec="seconds"), reminder_id),
            )
            return {"id": reminder_id, "texto": row["texto"], "horario": due, "status": status}

    def retirar_vencidos(self, limite: int = 30) -> list[dict]:
        """Marca em lote sob lock SQLite; uma instancia diferente nao duplica o aviso."""
        now = self._now().timestamp()
        with self._lock, self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute(
                "SELECT id, texto, horario, status FROM lembretes "
                "WHERE status='pendente' ORDER BY horario ASC LIMIT ?",
                (limite,),
            ).fetchall()
            vencidos = [row for row in rows if datetime.fromisoformat(row["horario"]).timestamp() <= now]
            stamp = self._now().isoformat(timespec="seconds")
            for row in vencidos:
                con.execute(
                    "UPDATE lembretes SET status='notificado', atualizado_em=? "
                    "WHERE id=? AND status='pendente'",
                    (stamp, row["id"]),
                )
            return [{**self._record(row), "status": "notificado"} for row in vencidos]


_singleton: ReminderStore | None = None
_singleton_lock = Lock()


def get_reminder_store() -> ReminderStore:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = ReminderStore()
        return _singleton


def criar_lembrete(texto: str, quando: str) -> ToolResult:
    try:
        reminder = get_reminder_store().criar(texto, quando)
    except (ValueError, OSError, sqlite3.Error) as exc:
        return ToolResult.failure(str(exc), error_code="reminder_error", tool_name="criar_lembrete")
    return ToolResult.success(
        f"Lembrete {reminder['id']} criado para {reminder['horario']}: {reminder['texto']}",
        data=reminder, tool_name="criar_lembrete",
    )


def listar_lembretes(status: str, limite: int) -> ToolResult:
    try:
        found = get_reminder_store().listar(status=status, limite=limite)
    except (ValueError, OSError, sqlite3.Error) as exc:
        return ToolResult.failure(str(exc), error_code="reminder_error", tool_name="listar_lembretes")
    return ToolResult.success(
        f"{len(found)} lembrete(s) encontrado(s).", data={"lembretes": found}, tool_name="listar_lembretes",
    )


def gerenciar_lembrete(id: int, acao: str, minutos: int) -> ToolResult:
    try:
        reminder = get_reminder_store().alterar(id, acao, minutos)
    except (ValueError, OSError, sqlite3.Error) as exc:
        return ToolResult.failure(str(exc), error_code="reminder_error", tool_name="gerenciar_lembrete")
    return ToolResult.success(
        f"Lembrete {id}: {reminder['status']}.", data=reminder, tool_name="gerenciar_lembrete",
    )
