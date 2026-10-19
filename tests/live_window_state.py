"""Explicit isolated desktop probe; no API, never targets a personal window."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from types import SimpleNamespace
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.permission_manager import PermissionManager
from tools.dispatcher import executar_ferramenta


def main():
    if '--run' not in sys.argv:
        raise SystemExit('Explicit --run required; creates and closes its own fixture window.')
    title = 'Auren isolated latency fixture ' + uuid.uuid4().hex[:10]
    root = tk.Tk()
    root.title(title)
    root.geometry('500x250')
    root.update()
    pm = PermissionManager()
    rows = []
    try:
        for name in ('maximizar_janela_windows', 'minimizar_janela_windows', 'restaurar_janela_windows'):
            pm.iniciar_tarefa()
            started = time.perf_counter()
            result = executar_ferramenta(SimpleNamespace(name=name, arguments=json.dumps({'alvo':title})), pm, None)
            rows.append({'tool':name, 'success':result.ok,
                'duration_ms':round((time.perf_counter()-started)*1000,3),
                'state':(result.data or {}).get('window_state',{}).get('observed'),
                'error_code':result.error_code})
            root.update()
    finally:
        root.destroy()
    print(json.dumps({'mode':'real_windows_isolated_fixture', 'api_cost_usd':0, 'results':rows}))
    return 0 if all(row['success'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
