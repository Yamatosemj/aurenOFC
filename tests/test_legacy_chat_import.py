"""Importacao de chats antigos: somente turnos, sem tocar em logs existentes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

from ui.conversation_history import UiConversationHistory
from ui.legacy_chat_import import legacy_uuid, read_legacy_sources


OLD = "chat-20261011-123230-219313"
OTHER = "chat-20261012-013200-123456"


def _event(kind: str, **fields: object) -> str:
    lines = ["[2026-10-11T12:32:30-03:00] " + kind]
    for name, val in fields.items():
        lines.append("  " + name + ": " + json.dumps(val, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _make_log(root: Path, cid: str, content: str) -> Path:
    path = root / cid / "chat" / "chat.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _make_memory(path: Path, chat_id: str = OLD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE conversas(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, papel TEXT, conteudo TEXT, criado_em TEXT)"
        )
        db.executemany(
            "INSERT INTO conversas(chat_id,papel,conteudo,criado_em) VALUES(?,?,?,?)",
            [
                (chat_id, "user", "Oi, Auren", "2026-10-11T12:32:30+00:00"),
                (chat_id, "assistant", "Olá! Posso ajudar?", "2026-10-11T12:32:31+00:00"),
                (chat_id, "user", "Abre a Steam", "2026-10-11T12:32:32+00:00"),
                (chat_id, "assistant", "A Steam foi aberta.", "2026-10-11T12:32:33+00:00"),
                (chat_id, "system", "INSTRUÇÕES INTERNAS NÃO MOSTRAR", "2026-10-11T12:32:33+00:00"),
            ],
        )


def test_legacy_logs_read_only_and_conversation_rows_only(tmp_path):
    root = tmp_path / "logs" / "chats"
    original = _make_log(root, OLD,
        _event("CHAT_START", chat_id=OLD)
        + _event("TASK_START", task_id="123", objetivo="Oi, Auren")
        + _event("MODEL_ROUND_RESPONSE", task_id="123", output_text="Texto interno de rodada")
        + _event("TOOL_CALL", ferramenta="abrir_programa", argumentos={"programa": "Steam"})
        + _event("TOOL_RESULT", resultado="Saída técnica interna")
        + _event("TASK_END", task_id="123", status="completed")
    )
    log_bytes = original.read_bytes()
    mem = tmp_path / "data" / "memory" / "auren_memory.sqlite3"
    _make_memory(mem)
    mem_bytes = mem.read_bytes()
    ui = UiConversationHistory(tmp_path / "data" / "ui" / "history.sqlite3", legacy_root=root, memory_db=mem)
    listed = ui.list_chats()
    assert len(listed) == 1
    assert listed[0]["title"] == "Oi, Auren"
    assert listed[0]["id"] == legacy_uuid(OLD)
    messages = ui.get_messages(listed[0]["id"])["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Oi, Auren"), ("assistant", "Olá! Posso ajudar?"),
        ("user", "Abre a Steam"), ("assistant", "A Steam foi aberta.")
    ]
    assert original.read_bytes() == log_bytes
    # SQLite original aberto em modo somente leitura.
    assert mem.read_bytes() == mem_bytes
    reopened = UiConversationHistory(ui.path, legacy_root=root, memory_db=mem)
    assert len(reopened.list_chats()) == 1
    assert len(reopened.get_messages(legacy_uuid(OLD))["messages"]) == 4


def test_fallback_log_only_shows_user_prompts_not_intermediate_model_output(tmp_path):
    root = tmp_path / "logs" / "chats"
    _make_log(root, OTHER,
        _event("CHAT_START", chat_id=OTHER)
        + _event("TASK_START", task_id="a", objetivo="Primeira pergunta")
        + _event("MODEL_ROUND_RESPONSE", task_id="a", output_text="Pensamento parcial, nao exibido")
        + _event("TOOL_RESULT", resultado="Texto de ferramenta não é resposta")
        + _event("TASK_END", task_id="a", status="completed")
        + _event("TASK_START", task_id="b", objetivo="Segunda pergunta")
        + _event("CHAT_END", chat_id=OTHER, status="closed")
    )
    ui = UiConversationHistory(tmp_path / "history.sqlite3", legacy_root=root, memory_db=tmp_path / "missing.db")
    chats = ui.list_chats()
    assert len(chats) == 1
    contents = [m["content"] for m in ui.get_messages(chats[0]["id"])["messages"]]
    assert contents == ["Primeira pergunta", "Segunda pergunta"]
    assert all(m["role"] == "user" for m in ui.get_messages(chats[0]["id"])["messages"])


def test_bad_log_values_never_became_messages(tmp_path):
    root = tmp_path / "logs" / "chats"
    _make_log(root, OLD,
        _event("TASK_START", objetivo={"object": "not a user message"})
        + "[2026-10-11T12:32:30-03:00] TASK_START\n  objetivo: \"incomplete...[truncated]\n"
        + _event("TASK_START", objetivo="Mensagem válida")
    )
    data = read_legacy_sources(root, tmp_path / "missing.sqlite3")
    assert data[OLD] == [("user", "Mensagem válida", "2026-10-11T12:32:30-03:00")]


def test_live_ui_chat_binding_prevents_duplicate_import_from_same_harness_session(tmp_path):
    root = tmp_path / "logs" / "chats"
    mem = tmp_path / "data" / "memory" / "auren_memory.sqlite3"
    _make_memory(mem)
    ui = UiConversationHistory(tmp_path / "history.sqlite3", legacy_root=root, memory_db=mem)
    # Uma leitura anterior ao vinculo pode ter criado a entrada antiga.
    assert len(ui.list_chats()) == 1
    current = ui.create_chat()
    ui.append(current, "user", "Oi, Auren")
    ui.bind_harness_chat(current, OLD)
    ui.append(current, "assistant", "Olá! Posso ajudar?")
    ui.refresh_legacy(force=True)
    chats = ui.list_chats()
    assert [c["id"] for c in chats] == [current]
    assert [m["content"] for m in ui.get_messages(current)["messages"]] == [
        "Oi, Auren", "Olá! Posso ajudar?"
    ]


def test_readonly_legacy_import_incremental_and_idempotent(tmp_path):
    root = tmp_path / "logs" / "chats"
    path = _make_log(root, OLD, _event("TASK_START", objetivo="Ola"))
    mem = tmp_path / "nonexistent.db"
    ui = UiConversationHistory(tmp_path / "history.sqlite3", legacy_root=root, memory_db=mem)
    first = ui.list_chats()[0]["id"]
    ui.refresh_legacy(force=True)
    assert len(ui.get_messages(first)["messages"]) == 1
    with path.open("a", encoding="utf-8") as f:
        f.write(_event("TASK_START", objetivo="Voltei"))
    ui.refresh_legacy(force=True)
    assert [m["content"] for m in ui.get_messages(first)["messages"]] == ["Ola", "Voltei"]


def test_history_http_automatically_discovers_old_chats_without_exposing_logs(tmp_path):
    """O painel consulta chats antigos pela API existente e recebe so mensagens."""
    from threading import Thread
    from http.client import HTTPConnection
    from ui.chrome_server import ChromeServer, LocalChromeApp
    from tests.test_ui_conversation_history import StubWorker

    root = tmp_path / "logs" / "chats"
    source = _make_log(
        root, OLD,
        _event("CHAT_START", chat_id=OLD)
        + _event("TASK_START", objetivo="Oi, Auren")
        + _event("MODEL_ROUND_RESPONSE", output_text="INTERNO_NAO_MOSTRAR")
        + _event("TOOL_CALL", ferramenta="abrir_programa", argumentos={"nome": "Chrome"}),
    )
    before = source.read_bytes()
    store = UiConversationHistory(
        tmp_path / "ui-history.sqlite3",
        legacy_root=root,
        memory_db=tmp_path / "missing.db",
    )
    app = LocalChromeApp(worker=StubWorker(), history_store=store)
    server = ChromeServer(app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path):
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            conn.request("GET", path, headers={"X-Auren-Token": app.token})
            res = conn.getresponse()
            return res.status, json.loads(res.read())
        finally:
            conn.close()

    try:
        status, listing = get("/api/history")
        assert status == 200 and len(listing["chats"]) == 1
        cid = listing["chats"][0]["id"]
        status, body = get("/api/history/" + cid)
        assert status == 200
        assert [(m["role"], m["content"]) for m in body["messages"]] == [
            ("user", "Oi, Auren")
        ]
        assert "INTERNO_NAO_MOSTRAR" not in json.dumps(body)
        assert "abrir_programa" not in json.dumps(body)
        assert source.read_bytes() == before
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
        thread.join(timeout=4)
