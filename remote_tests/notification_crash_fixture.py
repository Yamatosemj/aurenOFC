"""Hard process death in disposable data, never personal processes or API."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from core.routines import RoutineScheduler
from core.task_manager import TaskManager


def main():
    assert not os.environ.get('OPENAI_API_KEY')
    mode, directory = sys.argv[1], Path(sys.argv[2])
    directory.mkdir(parents=True, exist_ok=False)
    manager = TaskManager(db_path=directory/'tasks.sqlite3')
    service = RoutineScheduler(manager, clock=lambda: 100)
    execute = mode == 'uncertain'
    routine = service.register(chat_id='owner', objective='Fictitious reminder', due_at=100,
        expires_at=1000, mode='execute' if execute else 'suggest',
        allowed_calls=[{'name':'obter_audio_windows','arguments':{}}] if execute else [],
        model_budget=1 if execute else 0)
    service.authorize(routine['id'], chat_id='owner')
    def effect_then_die(*args, **kwargs):
        with (directory/'effects.txt').open('wb') as stream:
            stream.write(b'one fictitious effect\n')
            stream.flush()
            os.fsync(stream.fileno())
        os._exit(21)
    h = SimpleNamespace(task_manager=manager, _garantir_sessao_chat=lambda:'owner',
        processar_mensagem=effect_then_die) if execute else None
    service.tick(h, chat_id='owner')
    # No manager.close, worker queue, HTTP server or acknowledgement.
    os._exit(17)


if __name__ == '__main__':
    main()
