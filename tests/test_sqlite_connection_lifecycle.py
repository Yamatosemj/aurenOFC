import sqlite3
import pytest
from memory.store import PersistentMemoryStore
from core.task_trace import TaskTraceStore

@pytest.mark.parametrize('kind', ['memory', 'trace'])
def test_operation_closes_connection_and_commits(tmp_path, kind):
    path = tmp_path / 'test.sqlite3'
    store = PersistentMemoryStore(path) if kind == 'memory' else TaskTraceStore(path)
    connection = store._conexao if kind == 'memory' else store._connect
    with connection() as db:
        db.execute('CREATE TABLE lifecycle (value INTEGER)')
        db.execute('INSERT INTO lifecycle VALUES (1)')
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute('SELECT 1')
    with connection() as db:
        assert db.execute('SELECT value FROM lifecycle').fetchone()[0] == 1
    moved = path.with_suffix('.moved')
    path.rename(moved)  # Windows refuses this if SQLite still holds the file.

def test_memory_transaction_rollback_closes_connection(tmp_path):
    store = PersistentMemoryStore(tmp_path/'memory.sqlite3')
    with pytest.raises(RuntimeError):
        with store._conexao() as db:
            db.execute("INSERT INTO memorias (chave,valor,criado_em,atualizado_em) VALUES ('x','y','a','a')")
            raise RuntimeError('fixture')
    with store._conexao() as db:
        assert db.execute('SELECT count(*) FROM memorias').fetchone()[0] == 0
