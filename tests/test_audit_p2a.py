from types import SimpleNamespace
from threading import Event

import pytest

from core.harness_turn import _registrar_turno
from core.harness_strategy import _salvar_estrategia_em_background
from core.harness_round_input import _montar_input_da_rodada
from core.permission_manager import PermissionManager, PermissionLevel
from core.session import SessionContextManager
from memory.store import PersistentMemoryStore
from tools import file_intelligence as files


def test_aud010_refused_turn_has_safe_diagnostic():
    events = []
    context = SimpleNamespace(persiste=True, record_turn=lambda *a: {"ok": False, "erro": "valor ficticio privado"})
    _registrar_turno("user", "ficticio", context=context, chat_id="a", task_id="b",
                    write_log=lambda event, **kw: events.append((event, kw)))
    assert any(event == "MEMORY_ERROR" for event, _ in events)
    assert "valor ficticio privado" not in repr(events)


def test_aud010_refused_background_strategy_does_not_complete():
    callbacks = []
    context = SimpleNamespace(persiste=True, record_strategy=lambda *a, **kw: {"ok": False})
    queue = SimpleNamespace(submit=lambda goal, runner, **kw: callbacks.append(runner) or "ficticio")
    _salvar_estrategia_em_background("objetivo", [{"ferramenta": "ficticia"}], "resultado",
        context=context, background_queue=queue, task_id="a", chat_id="b", write_log=lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="recusad"):
        callbacks[0](Event())


def test_aud011_missing_chat_never_recovers_other_chat(tmp_path):
    store = PersistentMemoryStore(tmp_path / "fake.db")
    store.registrar_conversa("chat-a", "user", "projeto ALFA_FICTICIO")
    snapshot = SessionContextManager(store).build(None, "projeto")
    assert "ALFA_FICTICIO" not in snapshot.texto


def test_aud014_untrusted_content_requires_clipboard_confirmation():
    manager = PermissionManager()
    manager.registrar_fonte_nao_confiavel("ler_pagina")
    level, _ = manager.nivel_da_acao("definir_area_transferencia_windows", {"texto": "ficticio"})
    assert level is PermissionLevel.CONFIRM


def test_aud015_strategy_failure_is_not_presented_as_success(tmp_path):
    store = PersistentMemoryStore(tmp_path / "fake.db")
    store.salvar_estrategia("projeto ALFA", ["passo ficticio"], "nao funcionou", False, chat_id="a")
    rendered = SessionContextManager(store).build("a", "projeto ALFA").secao("estrategias")
    assert "falhou" in rendered.lower()
    assert "nao funcionou" in rendered


def test_aud015_context_is_carried_to_next_round():
    requests = []
    def state(*args, incluir_contexto):
        requests.append(incluir_contexto)
        return "restricao ficticia" if incluir_contexto else "sem contexto"
    result = _montar_input_da_rodada("objetivo", [], SimpleNamespace(output=[]), [],
        montar_estado=state, preparar_resultado_visual=lambda _: None, ao_atualizar_geometria=lambda: None)
    assert requests == [True]
    assert "restricao ficticia" in repr(result)


def test_aud023_copy_scan_does_not_hash_protected_target(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    main, candidate = root / "main.txt", root / "copy.txt"
    main.write_text("ficticio")
    candidate.write_text("ficticio")
    target = tmp_path / ".ssh" / "ficticio.txt"
    target.parent.mkdir()
    target.write_text("ficticio")
    original_resolve = type(candidate).resolve
    monkeypatch.setattr(type(candidate), "resolve", lambda path, *a, **kw: target if path == candidate else original_resolve(path, *a, **kw))
    monkeypatch.setattr(files, "_copy_search_roots", lambda: [root])
    monkeypatch.setattr(files, "_read_allowed_roots", lambda: [root])
    hashed = []
    monkeypatch.setattr(files, "_sha256", lambda path: hashed.append(path) or "same")
    result = files._history(main, "same", 5)
    assert not hashed
    assert not result.copias_confirmadas
