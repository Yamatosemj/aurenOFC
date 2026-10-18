"""Explicit, bounded schedules. Goal execution still belongs to the Harness."""
from contextlib import contextmanager
import json
from threading import Lock
import time
from types import SimpleNamespace
import uuid

from core.harness_serialization import _identidade_da_chamada
from core.tool_contracts import validate_tool_arguments


class RoutineScheduler:
    def __init__(self, manager, *, clock=time.time):
        self.manager, self.clock = manager, clock
        self._tick_lock = Lock()
        with manager._lock:
            if not manager.persistent or manager.closed:
                raise RuntimeError('Rotinas exigem TaskManager persistente aberto.')
            if getattr(manager, '_routine_scheduler_attached', False):
                raise RuntimeError('Ja existe um agendador neste manager.')
            with self._transaction() as connection:
                connection.execute('CREATE TABLE IF NOT EXISTS auren_routines (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, payload TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS auren_routine_events (seq INTEGER PRIMARY KEY, routine_id TEXT NOT NULL, operation TEXT NOT NULL, payload TEXT NOT NULL)')
                connection.execute('''CREATE TABLE IF NOT EXISTS auren_routine_notifications (
                    id TEXT PRIMARY KEY, routine_id TEXT NOT NULL, chat_id TEXT NOT NULL,
                    text TEXT NOT NULL, kind TEXT NOT NULL, task_id TEXT NOT NULL,
                    available_at INTEGER NOT NULL, revision INTEGER NOT NULL,
                    acknowledged_at INTEGER)''')
                connection.execute('''CREATE INDEX IF NOT EXISTS auren_notifications_pending
                    ON auren_routine_notifications(chat_id, acknowledged_at, available_at)''')
                for routine_id, payload in connection.execute('SELECT id, payload FROM auren_routines').fetchall():
                    value = self._decode(payload)
                    if value['id'] != routine_id:
                        raise RuntimeError('Identidade da rotina diverge do registro.')
                    if value['status'] == 'running':
                        value['status'] = 'interrupted'
                        self._put(connection, value, 'recover_uncertain')
                        self._queue_notification(connection, value, 'interrupted')
            manager._routine_scheduler_attached = True

    @contextmanager
    def _transaction(self):
        with self.manager._lock:
            if self.manager.closed:
                raise RuntimeError('Armazenamento de rotinas encerrado.')
            connection = self.manager._storage.connection
            with connection:
                yield connection

    @staticmethod
    def _decode(payload):
        value = json.loads(payload)
        fields = {'version', 'id', 'chat_id', 'objective', 'mode', 'next_due', 'expires_at',
                  'interval_seconds', 'runs_left', 'model_budget', 'allowed_calls', 'status', 'run_id', 'last_task_id'}
        if (not isinstance(value, dict) or set(value) != fields or type(value['version']) is not int or value['version'] != 1
                or any(not isinstance(value[k], str) for k in
                       ('id', 'chat_id', 'objective', 'mode', 'status', 'run_id', 'last_task_id'))
                or not value['id'] or not value['chat_id'] or not value['objective']
                or len(value['objective']) > 4000
                or value['mode'] not in {'suggest', 'execute'}
                or value['status'] not in {'draft', 'enabled', 'running', 'revoked', 'exhausted', 'expired', 'failed', 'interrupted'}
                or any(type(value[k]) is not int or value[k] < 0 for k in
                       ('next_due', 'expires_at', 'interval_seconds', 'runs_left', 'model_budget'))
                or value['runs_left'] > 1000 or value['model_budget'] > 20
                or (0 < value['interval_seconds'] < 60)
                or (not value['interval_seconds'] and value['runs_left'] > 1)
                or not isinstance(value['allowed_calls'], list) or len(value['allowed_calls']) > 20
                or len(json.dumps(value['allowed_calls'])) > 16000):
            raise RuntimeError('Registro de rotina invalido; nao executar.')
        for item in value['allowed_calls']:
            if (not isinstance(item, dict) or set(item) != {'name', 'arguments'}
                    or not isinstance(item['name'], str)
                    or not validate_tool_arguments(item['name'], item['arguments'])[0]):
                raise RuntimeError('Escopo da rotina invalido.')
        if value['mode'] == 'execute' and (not value['allowed_calls'] or not value['model_budget']):
            raise RuntimeError('Rotina executavel sem escopo/orcamento.')
        return value

    def _put(self, connection, value, operation):
        payload = json.dumps(value, ensure_ascii=False)
        self._decode(payload)
        connection.execute('INSERT INTO auren_routines VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                           (value['id'], value['chat_id'], payload))
        connection.execute('INSERT INTO auren_routine_events(routine_id,operation,payload) VALUES(?,?,?)',
                           (value['id'], operation, payload))

    def register(self, *, chat_id, objective, due_at, expires_at, interval_seconds=0,
                 max_runs=1, mode='suggest', allowed_calls=None, model_budget=0):
        if (not isinstance(chat_id, str) or not chat_id or not isinstance(objective, str)
                or not objective.strip() or len(objective) > 4000
                or any(type(v) is not int for v in (due_at, expires_at, interval_seconds, max_runs, model_budget))
                or due_at < 0 or expires_at <= due_at or not 1 <= max_runs <= 1000
                or interval_seconds < 0 or (interval_seconds and interval_seconds < 60)
                or (not interval_seconds and max_runs != 1)):
            raise ValueError('Agenda precisa de objetivo, prazo, intervalo e quantidade limitados.')
        value = dict(version=1, id=uuid.uuid4().hex, chat_id=chat_id, objective=objective.strip(),
            mode=mode, next_due=due_at, expires_at=expires_at, interval_seconds=interval_seconds,
            runs_left=max_runs, model_budget=model_budget, allowed_calls=allowed_calls or [],
            status='draft', run_id='', last_task_id='')
        try:
            self._decode(json.dumps(value))
        except RuntimeError as error:
            raise ValueError(str(error)) from error
        with self._transaction() as connection:
            if connection.execute('SELECT COUNT(*) FROM auren_routines WHERE chat_id=?', (chat_id,)).fetchone()[0] >= 1000:
                raise RuntimeError('Limite de rotinas por chat atingido.')
            self._put(connection, value, 'register_draft')
        return value

    def _get(self, connection, routine_id, chat_id):
        row = connection.execute('SELECT payload FROM auren_routines WHERE id=? AND chat_id=?', (routine_id, chat_id)).fetchone()
        if row is None:
            raise RuntimeError('Rotina nao encontrada neste chat.')
        value = self._decode(row[0])
        if value['id'] != routine_id or value['chat_id'] != chat_id:
            raise RuntimeError('Identidade da rotina invalida.')
        return value

    def get(self, routine_id, *, chat_id):
        with self._transaction() as connection:
            return self._get(connection, routine_id, chat_id)

    def list(self, *, chat_id):
        with self._transaction() as connection:
            ids = connection.execute('SELECT id FROM auren_routines WHERE chat_id=? ORDER BY rowid LIMIT 1000', (chat_id,)).fetchall()
            return [self._get(connection, row[0], chat_id) for row in ids]

    def authorize(self, routine_id, *, chat_id):
        with self._transaction() as connection:
            value = self._get(connection, routine_id, chat_id)
            if value['status'] != 'draft' or self.clock() >= value['expires_at']:
                raise RuntimeError('Somente rascunho vigente pode ser autorizado explicitamente.')
            value['status'] = 'enabled'
            self._put(connection, value, 'user_authorize')
            return value

    def revoke(self, routine_id, *, chat_id):
        with self._transaction() as connection:
            value = self._get(connection, routine_id, chat_id)
            value['status'] = 'revoked'
            self._put(connection, value, 'user_revoke')
            return value

    def _scope(self, value):
        allowed = {(entry['name'], _identidade_da_chamada(SimpleNamespace(
            arguments=json.dumps(entry['arguments'])))) for entry in value['allowed_calls']}
        def check(item):
            current = self.get(value['id'], chat_id=value['chat_id'])
            return (current['status'] == 'running' and current['run_id'] == value['run_id']
                    and self.clock() < current['expires_at']
                    and (str(getattr(item, 'name', '')), _identidade_da_chamada(item)) in allowed)
        return check

    def _queue_notification(self, connection, value, kind):
        # The occurrence ID is also the delivery ID: redelivery cannot claim a run.
        connection.execute('''INSERT INTO auren_routine_notifications
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL) ON CONFLICT(id) DO NOTHING''',
            (value['run_id'], value['id'], value['chat_id'], value['objective'], kind,
             value['last_task_id'], int(self.clock())))

    def pending_notifications(self, *, chat_id):
        with self._transaction() as connection:
            rows = connection.execute('''SELECT id, routine_id, text, kind, task_id,
                available_at, revision FROM auren_routine_notifications
                WHERE chat_id=? AND acknowledged_at IS NULL AND available_at<=?
                ORDER BY available_at, rowid LIMIT 50''', (chat_id, int(self.clock()))).fetchall()
            keys = ('id', 'routine_id', 'text', 'kind', 'task_id', 'available_at', 'revision')
            return [dict(zip(keys, row)) for row in rows]

    @staticmethod
    def _notification(connection, notification_id, revision, chat_id):
        if (not isinstance(notification_id, str) or not notification_id or len(notification_id) > 200
                or type(revision) is not int or revision < 1):
            raise ValueError('Identidade de aviso invalida.')
        row = connection.execute('''SELECT revision, available_at FROM auren_routine_notifications
            WHERE id=? AND chat_id=?''', (notification_id, chat_id)).fetchone()
        if row is None:
            raise RuntimeError('Aviso nao encontrado neste chat.')
        return row

    def acknowledge_notification(self, notification_id, revision, *, chat_id):
        with self._transaction() as connection:
            current, due = self._notification(connection, notification_id, revision, chat_id)
            now = int(self.clock())
            if current != revision or due > now:
                return False
            connection.execute('''UPDATE auren_routine_notifications
                SET acknowledged_at=COALESCE(acknowledged_at, ?) WHERE id=? AND chat_id=? AND revision=?''',
                (now, notification_id, chat_id, revision))
            return True

    def snooze_notification(self, notification_id, revision, *, chat_id, seconds=600):
        # Delay delivery only. Never re-enable or execute the underlying routine.
        if type(seconds) is not int or not 60 <= seconds <= 604800:
            raise ValueError('Adiamento deve ser de 60 segundos a 7 dias.')
        with self._transaction() as connection:
            current, due = self._notification(connection, notification_id, revision, chat_id)
            now = int(self.clock())
            if current != revision or due > now:
                return False
            connection.execute('''UPDATE auren_routine_notifications SET acknowledged_at=NULL,
                available_at=?, revision=revision+1 WHERE id=? AND chat_id=? AND revision=?''',
                (now + seconds, notification_id, chat_id, revision))
            return True

    def tick(self, harness, *, chat_id):
        # No thread, model, network or external notification starts implicitly.
        if not self._tick_lock.acquire(blocking=False):
            return []
        try:
            now = int(self.clock())
            for candidate in sorted(self.list(chat_id=chat_id), key=lambda item: item['next_due']):
                with self._transaction() as connection:
                    value = self._get(connection, candidate['id'], chat_id)
                    if value['status'] != 'enabled' or value['next_due'] > now:
                        continue
                    if now >= value['expires_at']:
                        value['status'] = 'expired'
                        self._put(connection, value, 'expire')
                        continue
                    if value['mode'] == 'execute' and harness is None:
                        continue
                    if value['mode'] == 'execute' and (getattr(harness, 'task_manager', None) is not self.manager
                            or harness._garantir_sessao_chat() != chat_id):
                        raise RuntimeError('Rotina exige o mesmo manager e o chat autorizado ativo.')
                    value['runs_left'] -= 1
                    value['run_id'] = uuid.uuid4().hex
                    value['next_due'] = now + value['interval_seconds']
                    value['status'] = 'running'
                    self._put(connection, value, 'claim_before_effect')
                    if value['mode'] == 'suggest':
                        # Claim, pending delivery and consumption commit together.
                        self._queue_notification(connection, value, 'suggestion')
                        value['status'] = ('enabled' if value['runs_left'] and value['interval_seconds'] else 'exhausted')
                        self._put(connection, value, 'finish')
                        return [{'routine_id': value['id'], 'kind': 'suggestion', 'text': value['objective']}]
                event = {'routine_id': value['id'], 'kind': 'suggestion', 'text': value['objective']}
                if value['mode'] == 'execute':
                    try:
                        harness.processar_mensagem(value['objective'], execution_scope=self._scope(value),
                                                   model_budget=value['model_budget'])
                        task = harness.current_task()
                        value['last_task_id'] = task.task_id
                        event['task_id'] = task.task_id
                        event['kind'] = task.state.value
                        if event['kind'] == 'completed' and not any(step.success is True for step in task.steps):
                            # Delivery must not advertise a model-only answer as
                            # proof that an executable routine actually ran.
                            event['kind'] = 'unverified'
                    except Exception:
                        event['kind'] = 'failed'
                with self._transaction() as connection:
                    current = self._get(connection, value['id'], chat_id)
                    if current['status'] == 'running' and current['run_id'] == value['run_id']:
                        current['last_task_id'] = value['last_task_id']
                        current['status'] = ('failed' if event['kind'] not in {'suggestion', 'completed'} else
                                             'enabled' if current['runs_left'] and current['interval_seconds'] else 'exhausted')
                        self._put(connection, current, 'finish')
                    self._queue_notification(connection, value, event['kind'])
                return [event]
            return []
        finally:
            self._tick_lock.release()
