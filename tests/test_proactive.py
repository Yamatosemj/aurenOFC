from pathlib import Path

from core.proactive import criar_resumo_sessao, preparar_abertura
from memory.store import PersistentMemoryStore


def _store(tmp_path: Path) -> PersistentMemoryStore:
    return PersistentMemoryStore(tmp_path / "memory.sqlite3")


def test_session_summary_is_short_and_uses_persisted_turns(tmp_path):
    store = _store(tmp_path)
    store.registrar_conversa("chat-1", "user", "Trabalhei na memória do Auren")
    store.registrar_conversa("chat-1", "assistant", "Certo")
    store.registrar_conversa("chat-1", "user", "Depois ajustei o Browser")
    store.registrar_conversa("chat-1", "assistant", "Feito")

    resumo = criar_resumo_sessao(store, "chat-1")

    assert resumo.startswith("Na última sessão")
    assert "memória do Auren" in resumo
    assert "Browser" in resumo
    assert len(resumo) <= 360


def test_session_summary_is_consumed_only_once(tmp_path):
    store = _store(tmp_path)
    store.salvar_resumo_sessao("chat-1", "Na última sessão, você trabalhou no Auren.")

    assert preparar_abertura(store) == "Na última sessão, você trabalhou no Auren."
    assert preparar_abertura(store) == ""


def test_proactive_monitoring_is_disabled_by_default(tmp_path):
    store = _store(tmp_path)

    assert store.obter_monitoramento_proativo()["ativo"] is False
    assert store.pode_checar_monitoramento_hoje() is False


def test_proactive_monitoring_can_be_enabled_and_is_daily(tmp_path):
    store = _store(tmp_path)
    store.definir_monitoramento_proativo(True)

    assert store.pode_checar_monitoramento_hoje() is True
    store.marcar_monitoramento_checado()
    assert store.pode_checar_monitoramento_hoje() is False


def test_topics_do_not_activate_monitoring(tmp_path):
    store = _store(tmp_path)

    assert store.adicionar_topico_proativo("Auren")["ok"] is True
    assert store.listar_topicos_proativos() == ["Auren"]
    assert store.obter_monitoramento_proativo()["ativo"] is False


def test_topic_can_be_removed(tmp_path):
    store = _store(tmp_path)
    store.adicionar_topico_proativo("Auren")

    assert store.remover_topico_proativo("Auren")["ok"] is True
    assert store.listar_topicos_proativos() == []
