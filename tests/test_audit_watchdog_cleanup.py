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
        if info_class == 3:
            return True  # No descendants in this accounting-only fixture.
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


@pytest.mark.parametrize('wait_result', [0, 258, 0xffffffff])
def test_zero_accounting_does_not_replace_waiting_for_descendant(monkeypatch, wait_result):
    """A contagem pode zerar antes de o handle do descendente sinalizar."""
    events = []
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'fixture'), raising=False)
    def query(handle, kind, buffer, size, returned):
        if kind == 3:
            info = ctypes.cast(buffer, ctypes.POINTER(watchdog.ProcessIdList)).contents
            info.NumberOfAssignedProcesses = info.NumberOfProcessIdsInList = 1
            info.ProcessIdList[0] = 456
        else:
            ctypes.cast(buffer, ctypes.POINTER(watchdog.BasicAccounting)).contents.ActiveProcesses = 0
        return True
    def wait(handle, timeout):
        events.append(('wait', handle))
        return wait_result
    def member(process, job, answer):
        ctypes.cast(answer, ctypes.POINTER(watchdog.wintypes.BOOL)).contents.value = True
        return True
    job = object.__new__(watchdog.WindowsJob)
    job.handle = 123
    job.api = SimpleNamespace(
        TerminateJobObject=lambda *args: events.append(('terminate', 123)) or True,
        QueryInformationJobObject=query, OpenProcess=lambda *args: 789,
        IsProcessInJob=member, WaitForSingleObject=wait,
        CloseHandle=lambda handle: events.append(('close', handle)) or True)
    if wait_result:
        with pytest.raises((TimeoutError, OSError)):
            job.terminate()
    else:
        job.terminate()
    assert ('wait', 789) in events
    assert events[-1] == ('close', 789)


@pytest.mark.parametrize('failure', ['query', 'open', 'identity'])
def test_enumeration_error_still_terminates_job(monkeypatch, failure):
    events = []
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'fixture'), raising=False)
    def query(handle, kind, buffer, size, returned):
        if failure == 'query':
            return False
        info = ctypes.cast(buffer, ctypes.POINTER(watchdog.ProcessIdList)).contents
        info.NumberOfAssignedProcesses = info.NumberOfProcessIdsInList = 1
        info.ProcessIdList[0] = 456
        return True
    def member(process, job, answer):
        ctypes.cast(answer, ctypes.POINTER(watchdog.wintypes.BOOL)).contents.value = False
        return True
    job = object.__new__(watchdog.WindowsJob)
    job.handle = 123
    job.api = SimpleNamespace(QueryInformationJobObject=query,
        OpenProcess=lambda *args: 0 if failure == 'open' else 789,
        IsProcessInJob=member,
        TerminateJobObject=lambda *args: events.append('terminate') or True,
        CloseHandle=lambda handle: events.append(('close', handle)) or True)
    with pytest.raises((OSError, RuntimeError)):
        job.terminate()
    assert events.count('terminate') == 1
    if failure == 'identity':
        assert events[-1] == ('close', 789)
