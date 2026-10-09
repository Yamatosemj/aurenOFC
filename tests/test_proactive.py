from pathlib import Path
import ast

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


def test_proactive_tools_are_registered_with_safe_permissions():
    from core.permission_manager import PermissionLevel, PermissionManager
    from core.tools_registry import tools

    names = {item["name"] for item in tools}
    assert {
        "configurar_monitoramento_proativo",
        "adicionar_topico_proativo",
        "remover_topico_proativo",
        "status_monitoramento_proativo",
    } <= names

    manager = PermissionManager(max_actions=10)
    assert manager.nivel("status_monitoramento_proativo") == PermissionLevel.AUTO
    assert manager.nivel("configurar_monitoramento_proativo") == PermissionLevel.CONFIRM


def test_daily_check_is_opt_in_and_once_per_day(monkeypatch, tmp_path):
    from core import proactive
    store = _store(tmp_path)
    store.adicionar_topico_proativo("Auren")
    calls = []
    def fake_search(query, mode):
        calls.append((query, mode))
        class Result:
            ok = True
            data = {"fontes": [{"trecho": "novidade"}]}
        return Result()
    assert proactive.checar_topicos(store, fake_search) == []
    assert calls == []
    store.definir_monitoramento_proativo(True)
    assert len(proactive.checar_topicos(store, fake_search)) == 1
    assert calls == [("Auren", "news")]
    assert proactive.checar_topicos(store, fake_search) == []
    assert len(calls) == 1

def test_proactive_nao_importa_tools_diretamente():
    codigo = Path("core/proactive.py").read_text(encoding="utf-8")
    arvore = ast.parse(codigo)
    imports = []
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(nome.startswith("tools.") for nome in imports)


def test_facade_version_matches_config():
    import auren
    from config import AUREN_VERSION, ARCHITECTURE_NAME, CACHE_KEY, MODEL

    assert auren.AUREN_VERSION == AUREN_VERSION
    assert auren.MODEL == MODEL
    assert auren.CACHE_KEY == CACHE_KEY
    assert auren.ARCHITECTURE_NAME == ARCHITECTURE_NAME

