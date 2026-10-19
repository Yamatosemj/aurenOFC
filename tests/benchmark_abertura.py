"""Real discovery, intercepted launch, no API or personal app effects.

Run in a fresh process per revision. Not an end-to-end window readiness test.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--program', default='notepad.exe')
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from tools import applications
    from core.tool_result import from_legacy
    real_popen = subprocess.Popen
    counts = {'discovery_processes': 0, 'intercepted_launches': 0}
    def popen(argv, **kwargs):
        if isinstance(argv, list) and Path(argv[0]).name.lower() in {'powershell', 'powershell.exe'}:
            counts['discovery_processes'] += 1
            return real_popen(argv, **kwargs)
        counts['intercepted_launches'] += 1
        return SimpleNamespace(pid=0)
    def startfile(*_):
        counts['intercepted_launches'] += 1
    started = time.perf_counter()
    with patch.object(subprocess, 'Popen', popen), patch.object(applications.os, 'startfile', startfile, create=True):
        result = from_legacy(applications.abrir_programa(args.program))
    print(json.dumps({'mode': 'real_discovery_intercepted_launch',
        'duration_ms': round((time.perf_counter()-started)*1000, 3),
        'success': result.ok, 'window_verified': False, **counts}))


if __name__ == '__main__':
    main()
