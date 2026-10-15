"""Regressoes do historico da UI; nao faz chamadas ao modelo ou a Windows."""
from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from queue import Queue
from threading import Thread
import json
import re
import shutil
import subprocess

import pytest

from ui.backend import UiEvent, ConfirmationChoice
from ui.conversation_history import UiConversationHistory, MAX_TEXT, PAGE_SIZE
from ui.chrome_server import ChromeServer, LocalChromeApp, INDEX_PATH


class StubWorker:
    def __init__(self):
        self.events = Queue()
        self.messages = []
        self.enabled = False
        self.off_calls = 0
        self.closed = False

    def start(self):
        pass

    def activate(self):
        self.enabled = True

    def submit(self, text):
        if not self.enabled:
            return False
        self.messages.append(text)
        return True

    def go_off(self):
        self.off_calls += 1
        self.enabled = False

    def close(self):
        self.closed = True


@contextmanager
def server_for(tmp_path):
    worker = StubWorker()
    store = UiConversationHistory(tmp_path / "history.sqlite3")
    app = LocalChromeApp(worker=worker, history_store=store)
    server = ChromeServer(app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, worker, store, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
        thread.join(timeout=4)


def call(port, method, path, token=None, body=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if token:
        headers["X-Auren-Token"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def test_history_survives_reopening_and_searches_content_without_sql_wildcards(tmp_path):
    path = tmp_path / "private" / "conversations.sqlite3"
    store = UiConversationHistory(path)
    one = store.create_chat()
    store.append(one, "user", "Abrir o Firefox")
    store.append(one, "assistant", "O Firefox está aberto.")
    another = store.create_chat()
    store.append(another, "user", "Estudar eletrônica")
    assert [c["id"] for c in store.list_chats()] == [another, one]
    assert [c["id"] for c in store.list_chats("Firefox")] == [one]
    assert store.list_chats("%") == []
    assert store.list_chats("_") == []
    assert "Abrir o Firefox" == UiConversationHistory(path).get_messages(one)["messages"][0]["content"]
    assert store.get_messages(one)["chat"]["title"] == "Abrir o Firefox"


def test_history_pagination_complete_without_truncation(tmp_path):
    store = UiConversationHistory(tmp_path / "history.sqlite3")
    chat = store.create_chat()
    for i in range(PAGE_SIZE + 7):
        store.append(chat, "assistant", f"Resposta {i}")
    first = store.get_messages(chat)
    assert len(first["messages"]) == PAGE_SIZE and first["has_more"]
    second = store.get_messages(chat, after=first["next_after"])
    assert len(second["messages"]) == 7 and not second["has_more"]
    assert second["messages"][-1]["content"] == f"Resposta {PAGE_SIZE+6}"
    with pytest.raises(ValueError):
        store.get_messages("../../bad")
    with pytest.raises(ValueError):
        store.get_messages(chat, after=-1)
    with pytest.raises(ValueError):
        store.append(chat, "user", "x" * (MAX_TEXT + 1))


def test_http_auth_persistence_copy_data_and_new_chat(tmp_path):
    with server_for(tmp_path) as (app, worker, store, port):
        status, _ = call(port, "GET", "/api/history")
        assert status == 403
        status, _ = call(port, "POST", "/api/history/new", body={})
        assert status == 403
        status, result = call(port, "POST", "/api/message", app.token, {"text": "Olá, Auren"})
        assert status == 200 and result == {"accepted": True, "mode": "active"}
        chat_id = app.active_chat_id
        assert chat_id
        worker.events.put(UiEvent("reply", "Olá, usuário!"))
        worker.events.put(UiEvent("idle"))
        status, snapshot = call(port, "GET", "/api/events?after=0", app.token)
        assert status == 200 and snapshot["active_chat_id"] == chat_id
        status, items = call(port, "GET", "/api/history?q=ol%C3%A1", app.token)
        assert status == 200 and len(items["chats"]) == 1
        assert items["chats"][0]["id"] == chat_id
        status, data = call(port, "GET", "/api/history/" + chat_id, app.token)
        assert status == 200
        assert [(r["role"], r["content"]) for r in data["messages"]] == [
            ("user", "Olá, Auren"), ("assistant", "Olá, usuário!")
        ]
        assert app.active_chat_id == chat_id

        status, new = call(port, "POST", "/api/history/new", app.token, {})
        assert status == 200 and new["active_chat_id"] is None
        assert worker.off_calls == 1
        assert app.active_chat_id is None
        assert store.get_messages(chat_id)["messages"][0]["content"] == "Olá, Auren"
        assert call(port, "GET", "/api/history/invalid", app.token)[0] == 400
        assert call(port, "GET", "/api/history?q=x&evil=1", app.token)[0] == 400
        assert call(port, "POST", "/api/history/new", app.token, {"unexpected": True})[0] == 400


def test_cannot_new_chat_during_work_or_confirmation(tmp_path):
    with server_for(tmp_path) as (app, worker, _, port):
        app.submit("Executar tarefa")
        status, _ = call(port, "POST", "/api/history/new", app.token, {})
        assert status == 400
        worker.events.put(UiEvent("idle"))
        app.snapshot()
        choice = ConfirmationChoice("Excluir", "Ação protegida", "excluir")
        worker.events.put(UiEvent("confirm", payload=choice))
        app.snapshot()
        status, _ = call(port, "POST", "/api/history/new", app.token, {})
        assert status == 400
        assert not choice.decided.is_set()
        app.shutdown()
        assert choice.decided.is_set() and not choice.approved


def test_exit_command_does_not_leak_to_model_or_reuse_old_history(tmp_path):
    with server_for(tmp_path) as (app, worker, store, port):
        first = app.submit("Primeiro assunto")["active_chat_id"]
        assert app.submit("sair")["mode"] == "off"
        second = app.submit("Outro assunto")["active_chat_id"]
        assert first != second
        assert worker.messages == ["Primeiro assunto", "Outro assunto"]
        assert len(store.list_chats()) == 2


def test_electron_clipboard_bridge_is_write_only_and_sandboxed():
    root = Path(__file__).resolve().parents[1] / "desktop" / "electron"
    main = (root / "main.cjs").read_text(encoding="utf-8")
    preload = (root / "preload.cjs").read_text(encoding="utf-8")
    assert "contextIsolation: true" in main and "sandbox: true" in main
    assert "preload: path.join(__dirname, 'preload.cjs')" in main
    assert "event.sender !== window.webContents" in main
    assert "value.length > 4_000_000" in main
    assert "clipboard.writeText(value)" in main
    assert "clipboard.readText" not in main + preload
    assert "contextBridge.exposeInMainWorld" in preload
    assert "auren:copy-text" in preload
    assert "window.aurenDesktop.copyText(text)" in INDEX_PATH.read_text(encoding="utf-8")
    node = shutil.which("node")
    if node:
        for path in (root / "main.cjs", root / "preload.cjs"):
            checked = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True, text=True, timeout=10, check=False,
            )
            assert checked.returncode == 0, checked.stderr


def test_history_drawer_uses_text_content_and_leaves_orb_shaders_untouched():
    source = INDEX_PATH.read_text(encoding="utf-8")
    assert "historySidebar" in source
    assert "historyToggle" in source and "historyCopyAll" in source
    assert "historyClipboard" in source and "historyLoadAll" in source
    assert "historyNew" in source and "/api/history/new" in source
    assert 'content.textContent=msg.content' in source
    assert "innerHTML" not in source
    assert "THREE.WebGLRenderer" in source
    assert "const VS=" in source and "const FS=" in source
    assert len(re.findall(r'<script nonce="__AUREN_SCRIPT_NONCE__">', source)) == 1
    node = shutil.which("node")
    if not node:
        pytest.skip("Node nao instalado")
    script = re.findall(r"<script[^>]*>([\s\S]*?)</script>", source, re.I)
    inline = [s for s in script if s.strip()]
    assert len(inline) == 1
    result = subprocess.run(
        [node, "--check", "-"], input=inline[0],
        text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
