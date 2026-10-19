"""Real SQLite transition cost versus retained task history, without a model."""
import argparse
import gc
import json
from pathlib import Path
import tempfile
import time
from core.task_manager import TaskManager
from scripts.diagnosticos.benchmark_usabilidade import stats

def run():
    groups = {}
    with tempfile.TemporaryDirectory(prefix='auren-persistence-') as folder:
        for count in (1, 30, 100):
            manager = TaskManager(db_path=Path(folder)/f'{count}.sqlite3', max_history=110)
            try:
                for n in range(count):
                    manager.create('Completed fixture', task_id=str(n), chat_id='fixture')
                    manager.start()
                    manager.complete('fixture')
                manager.create('Active fixture', chat_id='fixture')
                manager.start()
                wall, cpu = [], []
                for _ in range(30):
                    started, cpu_started = time.perf_counter(), time.process_time()
                    manager.wait_for_model()
                    manager.resume()
                    wall.append((time.perf_counter()-started)*1000)
                    cpu.append((time.process_time()-cpu_started)*1000)
                groups[str(count)] = {'pair_wall_ms': stats(wall), 'pair_cpu_ms': stats(cpu)}
            finally:
                manager.close()
        gc.collect()
    return {'kind': 'offline_real_task_manager_real_sqlite', 'history_sizes': groups}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run(), indent=2), encoding='utf-8')
