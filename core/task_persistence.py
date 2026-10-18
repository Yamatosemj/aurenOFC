"""Armazenamento do TaskManager; nao planeja, autoriza nem executa ferramentas."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3


class TaskStorage:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        if self.path.is_file() and self.path.stat().st_nlink > 1:
            raise RuntimeError('Banco de tarefas com multiplos vinculos; uso exclusivo nao comprovado.')
        if self.path.is_file() and self.path.stat().st_size == 0:
            raise RuntimeError('Arquivo existente vazio; nao iniciar historico novo silenciosamente.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        self._owner = None
        self._locked = False
        try:
            self._owner = self.path.with_suffix(self.path.suffix + '.lock').open('a+b')
            if self._owner.tell() == 0:
                self._owner.write(b'0')
                self._owner.flush()
            self._owner.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self._owner.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
            except OSError as exc:
                raise RuntimeError('Arquivo de tarefas ja esta em uso por outro manager.') from exc
            self.connection = sqlite3.connect(self.path, timeout=3, check_same_thread=False)
            version = self.connection.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('Versao do banco de tarefas nao suportada.')
            if version == 0:
                if self.connection.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone():
                    raise RuntimeError('Arquivo existente possui outro esquema; banco de tarefas recusado.')
                self.connection.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE tasks (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                                        terminal INTEGER NOT NULL);
                    CREATE TABLE task_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL, operation TEXT NOT NULL, at TEXT NOT NULL,
                        payload TEXT NOT NULL);
                    CREATE INDEX task_events_by_task ON task_events(task_id, sequence);
                    CREATE TABLE task_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    PRAGMA user_version=1;
                    COMMIT;
                ''')
        except BaseException:
            self.close()
            raise

    def load(self, limit):
        row = self.connection.execute("SELECT value FROM task_meta WHERE key='current'").fetchone()
        current = json.loads(row[0]) if row else None
        records = self.connection.execute('''
            SELECT task_id, payload FROM tasks WHERE terminal=0 OR task_id=? OR task_id IN
            (SELECT task_id FROM tasks ORDER BY rowid DESC LIMIT ?) ORDER BY rowid
        ''', (current, limit)).fetchall()
        return {key: json.loads(payload) for key, payload in records}, current

    def get(self, task_id):
        row = self.connection.execute('SELECT payload FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_ids(self, chat_id, limit, offset):
        return tuple(row[0] for row in self.connection.execute('''SELECT task_id FROM tasks
            WHERE json_extract(payload, '$.chat_id')=? ORDER BY rowid DESC LIMIT ? OFFSET ?''',
            (chat_id, limit, offset)))

    def list_chat_ids(self):
        chats = {row[0] for row in self.connection.execute("SELECT DISTINCT json_extract(payload, '$.chat_id') FROM tasks") if row[0]}
        if self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auren_routines'").fetchone():
            chats.update(row[0] for row in self.connection.execute('SELECT DISTINCT chat_id FROM auren_routines'))
        return tuple(sorted(chats))

    def save(self, records, current, operation, previous):
        with self.connection:
            for key, record in records.items():
                if record == previous.get(key):
                    continue
                payload = json.dumps(record, ensure_ascii=False)
                terminal = record['state'] in {'completed', 'failed', 'cancelled'}
                self.connection.execute('''
                    INSERT INTO tasks VALUES (?, ?, ?) ON CONFLICT(task_id) DO UPDATE SET
                    payload=excluded.payload, terminal=excluded.terminal
                ''', (key, payload, terminal))
                self.connection.execute('''INSERT INTO task_events
                    (task_id, operation, at, payload) VALUES (?, ?, ?, ?)''',
                    (key, operation, datetime.now(timezone.utc).isoformat(), payload))
            self.connection.execute('''INSERT INTO task_meta VALUES ('current', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value''', (json.dumps(current),))

    def history(self, task_id, *, after_sequence=0, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000 or type(after_sequence) is not int or after_sequence < 0:
            raise ValueError('Paginacao de historico invalida.')
        rows = self.connection.execute('''SELECT sequence, operation, at, payload FROM task_events
            WHERE task_id=? AND sequence>? ORDER BY sequence LIMIT ?''',
            (task_id, after_sequence, limit)).fetchall()
        return tuple({'sequence':seq, 'operation':operation, 'at':at, 'record':json.loads(payload)}
                     for seq, operation, at, payload in rows)

    def close(self):
        try:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
        finally:
            if self._owner is not None:
                try:
                    if self._locked:
                        self._owner.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(self._owner.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(self._owner.fileno(), fcntl.LOCK_UN)
                finally:
                    self._owner.close()
                    self._owner = None
                    self._locked = False
