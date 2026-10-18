from datetime import datetime, timezone
from pathlib import Path
import os
import pytest

from memory.store import PersistentMemoryStore


def test_aud019_forget_describes_its_limited_scope(tmp_path):
    store = PersistentMemoryStore(tmp_path / 'fictional.sqlite3')
    store.salvar('cor fictícia', 'azul')
    store.registrar_conversa('chat', 'user', 'cor fictícia azul')
    result = store.esquecer('cor fictícia')
    assert result['ok']
    assert result.get('escopo') == 'fato_salvo'
    assert 'conversas' in result.get('aviso', '').lower()
    assert store.ultimas_conversas('chat')['resultados']


def test_aud019_retention_previews_then_deletes_only_expired_classes(tmp_path):
    from core.retention import aplicar_retencao
    store = PersistentMemoryStore(tmp_path / 'data/memory/auren_memory.sqlite3')
    store.salvar('cor fictícia', 'azul')
    store.registrar_conversa('chat', 'user', 'old fictional conversation')
    store.salvar_estrategia('old fictional strategy', ['passo'], 'ok', True, chat_id='chat')
    with store._conexao() as con:
        con.execute("UPDATE conversas SET criado_em='2020-01-01T00:00:00+00:00'")
        con.execute("UPDATE estrategias SET atualizado_em='2020-01-01T00:00:00+00:00'")
        con.commit()
    for relative in ('logs/chats/old.log', 'logs/tarefas/old.txt', 'runtime/screenshots/screen_old.png'):
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('fictional artifact')
        os.utime(file, (1_577_836_800, 1_577_836_800))
    fresh = tmp_path / 'logs/chats/new.log'
    fresh.write_text('fresh fictional log')
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    preview = aplicar_retencao(tmp_path, agora=now)
    assert preview['aplicado'] is False
    assert preview['contagens']['conversas'] == 1
    assert store.ultimas_conversas('chat')['resultados']
    result = aplicar_retencao(tmp_path, agora=now, confirmar=True)
    assert result['aplicado'] is True
    assert not store.ultimas_conversas('chat')['resultados']
    assert store.consultar('cor fictícia')['memorias']
    assert fresh.exists()
    assert not (tmp_path / 'logs/chats/old.log').exists()
    assert not (tmp_path / 'logs/tarefas/old.txt').exists()
    assert not (tmp_path / 'runtime/screenshots/screen_old.png').exists()


def test_aud019_trace_retention_preserves_active_tasks_and_cleans_spans(tmp_path):
    from core.retention import aplicar_retencao
    from core.task_trace import TaskTraceStore
    trace_store = TaskTraceStore(tmp_path / 'data/traces/auren_trace.sqlite3')
    old = trace_store.start_task(task_id='old', chat_id='fictional', objective='fictional')
    old.record_model(1, 1, {})
    old.finish(status='completed')
    trace_store.start_task(task_id='active', chat_id='fictional', objective='fictional')
    with trace_store._connect() as con:
        con.execute("UPDATE task_traces SET finished_at='2020-01-01T00:00:00Z' WHERE task_id='old'")
        con.commit()
    aplicar_retencao(tmp_path, confirmar=True)
    with trace_store._connect() as con:
        assert [row[0] for row in con.execute('SELECT task_id FROM task_traces')] == ['active']
        assert not con.execute('SELECT * FROM task_trace_spans').fetchall()


def test_aud019_linked_log_directory_is_refused(tmp_path, monkeypatch):
    from core.retention import aplicar_retencao
    logs = tmp_path / 'logs'
    logs.mkdir()
    file = logs / 'old.log'
    file.write_text('fictional')
    os.utime(file, (1, 1))
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == logs or original(path))
    result = aplicar_retencao(tmp_path, confirmar=True)
    assert result['recusados'] == 1 and file.exists()


def test_aud019_nonboolean_confirmation_is_rejected(tmp_path):
    from core.retention import aplicar_retencao
    with pytest.raises(ValueError, match='booleano'):
        aplicar_retencao(tmp_path, confirmar='sim')
