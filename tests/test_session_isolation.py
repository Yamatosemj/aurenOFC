
from pathlib import Path
from types import SimpleNamespace

from core.harness import AurenHarness
from core.session import SessionContextManager
from core.memory_context import recuperar_memoria
from memory.store import PersistentMemoryStore


def _harness(tmp_path, monkeypatch):
    import core.harness as harness_mod
    monkeypatch.setattr(harness_mod, "CHAT_LOGS_DIR", tmp_path / "chats")
    monkeypatch.setattr(harness_mod, "LOG_DIR", tmp_path / "logs")
    return AurenHarness(
        criar_resposta=lambda *_args, **_kwargs: SimpleNamespace(output=[], output_text="ok", usage=None),
        executar_ferramenta=lambda _item: "ok",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )


def test_two_harnesses_have_distinct_sessions(tmp_path, monkeypatch):
    a = _harness(tmp_path, monkeypatch)
    b = _harness(tmp_path, monkeypatch)
    aid = a._garantir_sessao_chat()
    bid = b._garantir_sessao_chat()
    assert aid != bid
    assert a._session is not b._session
    assert a._session.log_file != b._session.log_file


def test_memory_context_is_scoped_by_chat_id(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory.sqlite3")
    store.registrar_conversa("chat-A", "user", "marker-A unique")
    store.registrar_conversa("chat-B", "user", "marker-B unique")
    context_a = recuperar_memoria(store, "marker-A unique", chat_id="chat-A")
    context_b = recuperar_memoria(store, "marker-A unique", chat_id="chat-B")
    assert any("marker-A unique" in item["conteudo"] for item in context_a["conversas"])
    assert not any("marker-B unique" in item["conteudo"] for item in context_a["conversas"])
    assert not context_b["conversas"]


def test_persistent_memory_without_chat_scope_remains_global(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory.sqlite3")
    store.salvar("global-key", "global-value", "geral")
    assert store.consultar("global-key", limite=5)["total"] == 1


def test_strategy_saved_in_chat_a_is_not_visible_in_chat_b(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory.sqlite3")
    ctx = SessionContextManager(store)
    ctx.record_strategy("abrir planilha de orcamento", ["abrir_programa: ok"], "feito", True, chat_id="chat-A")
    snap_b = ctx.build("chat-B", "abrir planilha de orcamento")
    assert snap_b.secao("estrategias") == ""
    assert store.buscar_estrategias("planilha orcamento", chat_id="chat-B")["total"] == 0


def test_strategy_saved_in_chat_a_stays_available_in_chat_a(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory.sqlite3")
    ctx = SessionContextManager(store)
    ctx.record_strategy("abrir planilha de orcamento", ["abrir_programa: ok"], "feito", True, chat_id="chat-A")
    ctx.record_strategy("abrir planilha de orcamento", ["navegar_navegador: ok"], "feito", True, chat_id="chat-B")
    snap_a = ctx.build("chat-A", "abrir planilha de orcamento")
    assert "abrir_programa" in snap_a.secao("estrategias")
    assert "navegar_navegador" not in snap_a.secao("estrategias")
    assert store.buscar_estrategias("planilha orcamento", chat_id="chat-A")["total"] == 1


def test_strategy_store_without_chat_scope_stays_global_and_legacy_rows_are_hidden_from_chats(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    # Banco no formato anterior (sem coluna chat_id) com uma estrategia antiga.
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE estrategias (id INTEGER PRIMARY KEY AUTOINCREMENT, objetivo TEXT NOT NULL, passos TEXT NOT NULL,"
        " resultado TEXT NOT NULL DEFAULT '', sucesso INTEGER NOT NULL DEFAULT 0, criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL)"
    )
    con.execute("INSERT INTO estrategias (objetivo, passos, resultado, sucesso, criado_em, atualizado_em) VALUES ('tarefa legada de relatorio', '[\"p\"]', 'ok', 1, 't', 't')")
    con.commit(); con.close()
    store = PersistentMemoryStore(path)  # migra
    assert store.buscar_estrategias("relatorio")["total"] == 1                      # sem escopo: global (compat)
    assert store.buscar_estrategias("relatorio", chat_id="chat-A")["total"] == 0    # com escopo: nao vaza
    store.salvar_estrategia("novo relatorio", ["p"], "ok", True, chat_id="chat-A")
    assert store.buscar_estrategias("relatorio", chat_id="chat-A")["total"] == 1


def test_harness_grava_estrategia_com_o_chat_da_sessao(tmp_path, monkeypatch):
    import core.harness as harness_mod
    monkeypatch.setattr(harness_mod, "CHAT_LOGS_DIR", tmp_path / "chats")
    monkeypatch.setattr(harness_mod, "LOG_DIR", tmp_path / "logs")
    store = PersistentMemoryStore(tmp_path / "memory.sqlite3")
    harness = AurenHarness(
        criar_resposta=lambda *_a, **_k: SimpleNamespace(output=[], output_text="ok", usage=None),
        executar_ferramenta=lambda _item: "ok",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        context=SessionContextManager(store),
    )
    chat_id = harness._garantir_sessao_chat()
    harness._salvar_estrategia_em_background(
        "organizar downloads", [{"ferramenta": "listar_arquivos", "resultado": "ok"}], "feito", True
    )
    import time
    deadline = time.time() + 5
    while time.time() < deadline and not store.buscar_estrategias("organizar downloads", chat_id=chat_id)["total"]:
        time.sleep(0.02)
    assert store.buscar_estrategias("organizar downloads", chat_id=chat_id)["total"] == 1
    assert store.buscar_estrategias("organizar downloads", chat_id="outro-chat")["total"] == 0
