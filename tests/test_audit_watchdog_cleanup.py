"""Encerramento assincrono simulado; nao cria processos nem consulta Windows."""
import ctypes
from types import SimpleNamespace

import pytest

from remote_tests import windows_watchdog as watchdog


@pytest.mark.parametrize('mode', ['drain', 'timeout', 'query_error'])
def test_terminate_requires_observation_of_zero_active_processes(monkeypatch, mode):
    calls = []
    clock = [0.0]
    monkeypatch.setattr(watchdog.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(watchdog.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + 1))
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'erro Windows ficticio'), raising=False)
    def terminate(handle, code):
        calls.append('terminate')
        return True
    def query(handle, info_class, buffer, size, returned):
        calls.append('query')
        if mode == 'query_error':
            return False
        info = ctypes.cast(buffer, ctypes.POINTER(watchdog.BasicAccounting)).contents
        info.ActiveProcesses = 0 if mode == 'drain' and calls.count('query') >= 2 else 2
        return True
    job = object.__new__(watchdog.WindowsJob)
    job.handle = 123
    job.api = SimpleNamespace(TerminateJobObject=terminate, QueryInformationJobObject=query)
    if mode == 'timeout':
        with pytest.raises(TimeoutError):
            job.terminate()
    elif mode == 'query_error':
        with pytest.raises(OSError):
            job.terminate()
    else:
        job.terminate()
        assert calls == ['terminate', 'query', 'query']
