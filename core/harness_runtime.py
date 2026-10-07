"""Sessao e logging de runtime compartilhados pelo Harness."""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.harness_logging import (
    SENSITIVE_KEYS,
    TEXT_SENSITIVE_KEYS,
    USAGE_KEYS,
    _compact_json,
    _redact_value,
    _redact_free_text,
    _register_redaction_value,
    _runtime_redaction_values,
    _register_sensitive_values_from_object,
    _register_sensitive_values_from_json_text,
    _register_redaction_values_from_objective,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
CHAT_LOGS_DIR = LOG_DIR / "chats"
TASK_LOG_DIR = LOG_DIR / "tarefas"
LOG_FILE = LOG_DIR / "auren.log"

@dataclass(frozen=True)
class SessionContext:
    chat_id: str
    log_file: Path

    @property
    def log_root(self) -> Path:
        return self.log_file.parent.parent


_CURRENT_SESSION: contextvars.ContextVar[SessionContext | None] = contextvars.ContextVar(
    "auren_current_session", default=None
)
_LOG_LOCK = threading.RLock()


def _chat_id() -> str:
    return "chat-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _write_one_log_file(path: Path, event: str, details: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{timestamp}] {event}\n")
        for key, value in details.items():
            arquivo.write(f"  {key}: {_compact_json(value)}\n")


def _create_chat_session() -> SessionContext:
    CHAT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _runtime_redaction_values().clear()
    for _ in range(10):
        chat_id = _chat_id()
        chat_root = CHAT_LOGS_DIR / chat_id
        chat_log_dir = chat_root / "chat"
        try:
            chat_log_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        session = SessionContext(chat_id=chat_id, log_file=chat_log_dir / "chat.log")
        _write_one_log_file(session.log_file, "CHAT_START", {"chat_id": chat_id})
        return session
    raise RuntimeError("Nao foi possivel criar uma pasta unica para o chat atual.")


def start_chat_session() -> str:
    """Cria e vincula uma nova sessao ao contexto de execucao atual."""
    session = _create_chat_session()
    _CURRENT_SESSION.set(session)
    return session.chat_id


def end_chat_session(status: str = "closed") -> None:
    """Fecha a sessao vinculada ao contexto de execucao atual."""
    session = _CURRENT_SESSION.get()
    if session is None:
        return
    try:
        _write_log("CHAT_END", chat_id=session.chat_id, status=status)
    finally:
        _CURRENT_SESSION.set(None)
        _runtime_redaction_values().clear()


def current_chat_id() -> str | None:
    session = _CURRENT_SESSION.get()
    return session.chat_id if session is not None else None


def current_chat_log_path() -> Path | None:
    session = _CURRENT_SESSION.get()
    return session.log_file if session is not None else None


def _prepare_log_details(event: str, details: dict[str, Any]) -> dict[str, Any]:
    """Aplica redacoes especificas de logs sem alterar o comportamento das ferramentas."""
    prepared = dict(details)
    tool_name = str(prepared.get("ferramenta") or "").strip()

    # Registra qualquer texto sensivel presente nos argumentos estruturados antes
    # que eventos futuros possam reproduzi-lo em estado, respostas ou resultados.
    if event == "TOOL_CALL":
        _register_sensitive_values_from_json_text(prepared.get("argumentos"))

    if event == "TOOL_RESULT" and tool_name == "ler_area_transferencia_windows":
        resultado = prepared.get("resultado")
        if resultado is not None:
            texto = str(resultado)
            # O retorno bruto do clipboard nunca deve entrar no arquivo de log.
            if texto and not texto.startswith("[REDACTED clipboard:"):
                _register_redaction_value(texto)
                prepared["resultado"] = f"[REDACTED clipboard: {len(texto)} caracteres]"
            else:
                prepared["resultado"] = "[REDACTED clipboard: conteudo ocultado]"

    return prepared


def _write_log(event: str, **details: Any) -> None:
    try:
        with _LOG_LOCK:
            prepared = _prepare_log_details(event, details)

            # O chat.log canonico pertence a sessao vinculada ao contexto atual.
            session = _CURRENT_SESSION.get()
            if session is not None:
                _write_one_log_file(session.log_file, event, prepared)

            # Mantemos os logs legados da V43 para compatibilidade.
            _write_one_log_file(LOG_FILE, event, prepared)

            task_id = str(prepared.get("task_id") or "").strip()
            if task_id:
                _write_one_log_file(TASK_LOG_DIR / f"{task_id}.txt", event, prepared)
    except OSError:
        # Falha de logging nao pode derrubar uma tarefa do Auren.
        pass


