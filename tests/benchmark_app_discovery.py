"""Offline benchmark fixture, outside the production tool execution path."""
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools import applications

def benchmark(samples, stats):
    durations, counts = [], []
    for _ in range(samples):
        def fake_scan(*args, **kwargs):
            time.sleep(.002)  # simulated cost, not real Windows latency
            return SimpleNamespace(returncode=0, stdout='')
        with patch.object(applications.shutil, 'which', return_value=None), \
                patch.object(Path, 'exists', return_value=True), \
                patch.object(applications.subprocess, 'run', side_effect=fake_scan) as scan:
            start = time.perf_counter()
            applications.procurar_executavel('Programa Ficticio')
            durations.append((time.perf_counter()-start)*1000)
            counts.append(scan.call_count)
    return {'delay_ms_per_subprocess': 2, 'total_ms': stats(durations), 'subprocesses': stats(counts)}
