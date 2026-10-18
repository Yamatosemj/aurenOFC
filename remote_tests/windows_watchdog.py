"""Bound a Windows test process and all descendants, even if the supervisor dies.

The child starts suspended and is assigned to a non-inheritable Job Object before
any test code runs. Never kill by executable name or affect pre-existing apps.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


class BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class BasicAccounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in
                ("TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")]
    _fields_ += [(name, wintypes.DWORD) for name in
                 ("TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]


class ProcessIdList(ctypes.Structure):
    # The Job already restricts its entire tree to 64 active processes.
    _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD),
                ("NumberOfProcessIdsInList", wintypes.DWORD),
                ("ProcessIdList", ctypes.c_size_t * 64)]


class WindowsJob:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows Job Objects required; refusing uncontained execution")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        # Kill on last handle close; deny breakaway; bounded child count/memory.
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8 | 0x200
        limits.BasicLimitInformation.ActiveProcessLimit = 64
        limits.JobMemoryLimit = 4 * 1024**3
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def terminate(self):
        processes = []
        try:
            try:
                listing = ProcessIdList()
                if not self.api.QueryInformationJobObject(
                        self.handle, 3, ctypes.byref(listing), ctypes.sizeof(listing), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if listing.NumberOfAssignedProcesses > listing.NumberOfProcessIdsInList:
                    raise RuntimeError("Incomplete Job process list")
                for pid in listing.ProcessIdList[:listing.NumberOfProcessIdsInList]:
                    # Hold object identity through termination; never kill by PID.
                    process = self.api.OpenProcess(0x1000 | 0x100000, False, pid)
                    if not process:
                        if ctypes.get_last_error() == 87:  # Already exited.
                            continue
                        raise ctypes.WinError(ctypes.get_last_error())
                    processes.append(process)
                    member = wintypes.BOOL()
                    if not self.api.IsProcessInJob(process, self.handle, ctypes.byref(member)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if not member.value:
                        raise RuntimeError("Job process identity changed")
            finally:
                # Enumeration failure must never skip containment cleanup.
                if not self.api.TerminateJobObject(self.handle, 124):
                    raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic() + 5.0
            for process in processes:
                state = self.api.WaitForSingleObject(
                    process, max(0, int((deadline - time.monotonic()) * 1000)))
                if state == 258:
                    raise TimeoutError("Job process termination not confirmed")
                if state != 0:
                    raise ctypes.WinError(ctypes.get_last_error())
            self._wait_empty(deadline)
        finally:
            for process in processes:
                self.api.CloseHandle(process)

    def _wait_empty(self, deadline):
        # Termination is asynchronous; waiting only for the parent is insufficient.
        while True:
            accounting = BasicAccounting()
            if not self.api.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if accounting.ActiveProcesses == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("Job still has active processes after termination")
            time.sleep(0.01)


def supervise(command, *, cwd, log_path, wall_seconds=1200, idle_seconds=120,
              max_log_bytes=16 * 1024**2, stop_file=None, stdin_path=None):
    """Return diagnostics; always close the job, including on cancellation/error."""
    import _winapi
    import msvcrt

    if not command or not (0 < wall_seconds <= 1200) or not (0 < idle_seconds <= 120):
        raise ValueError("Invalid watchdog limits")
    if not (0 < max_log_bytes <= 16 * 1024**2):
        raise ValueError("Invalid log limit")
    if stop_file and Path(stop_file).exists():
        return {"reason": "emergency_stop", "exit_code": 124, "pid": None, "duration_seconds": 0}
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    job = WindowsJob()
    process = thread = None
    started = time.monotonic()
    last_progress = started
    last_size = 0
    last_notice = started
    result = {"reason": "startup_error", "exit_code": 125, "pid": None}
    try:
        with log_path.open("wb", buffering=0) as output, open(stdin_path or os.devnull, "rb") as stdin:
            out_handle = msvcrt.get_osfhandle(output.fileno())
            in_handle = msvcrt.get_osfhandle(stdin.fileno())
            os.set_handle_inheritable(out_handle, True)
            os.set_handle_inheritable(in_handle, True)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESTDHANDLES
            startup.hStdOutput = startup.hStdError = out_handle
            startup.hStdInput = in_handle
            # Only these stdio handles are inherited. The job handle stays private.
            startup.lpAttributeList = {"handle_list": [out_handle, in_handle]}
            environment = os.environ.copy()
            environment.update(PYTHONUNBUFFERED="1", PYTHONUTF8="1", AUREN_TEST_MODE="1")
            process, thread, pid, _tid = _winapi.CreateProcess(
                None, subprocess.list2cmdline([str(arg) for arg in command]),
                None, None, True, 0x4 | subprocess.CREATE_NO_WINDOW,
                environment, str(cwd), startup)
            result["pid"] = pid
            if not job.api.AssignProcessToJobObject(job.handle, process):
                _winapi.TerminateProcess(process, 125)
                raise ctypes.WinError(ctypes.get_last_error())
            if job.api.ResumeThread(thread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
            _winapi.CloseHandle(thread)
            thread = None
            while True:
                now = time.monotonic()
                size = log_path.stat().st_size
                if size != last_size:
                    last_progress, last_size = now, size
                    if now - last_notice >= 5:
                        print("[WATCHDOG] Test process produced output", flush=True)
                        last_notice = now
                reason = None
                if stop_file and Path(stop_file).exists():
                    reason = "emergency_stop"
                elif size >= max_log_bytes:
                    reason = "log_limit"
                elif now - started >= wall_seconds:
                    reason = "wall_timeout"
                elif now - last_progress >= idle_seconds:
                    reason = "idle_timeout"
                if reason:
                    result.update(reason=reason, exit_code=124)
                    break
                state = _winapi.WaitForSingleObject(process, 100)
                if state == _winapi.WAIT_OBJECT_0:
                    result.update(reason="completed", exit_code=_winapi.GetExitCodeProcess(process))
                    break
                if state != _winapi.WAIT_TIMEOUT:
                    raise RuntimeError("Process wait failed")
        # On success also close the job: no orphaned test browsers/windows survive.
    except KeyboardInterrupt:
        result.update(reason="cancelled", exit_code=130)
    finally:
        try:
            job.terminate()
        except Exception as exc:
            result.update(reason="cleanup_failed", exit_code=125, cleanup_error=type(exc).__name__)
        finally:
            job.close()
        if thread is not None:
            _winapi.CloseHandle(thread)
        if process is not None:
            if _winapi.WaitForSingleObject(process, 5000) != _winapi.WAIT_OBJECT_0:
                result.update(reason="cleanup_failed", exit_code=125, cleanup_error="ProcessWaitTimeout")
            _winapi.CloseHandle(process)
        result["duration_seconds"] = round(time.monotonic() - started, 2)
        if log_path.exists() and log_path.stat().st_size > max_log_bytes:
            with log_path.open("r+b") as output:
                output.truncate(max_log_bytes)
        # Artifacts are files: GitHub's console masking does not redact them.
        secret = os.environ.get("OPENAI_API_KEY", "")
        if secret and log_path.exists():
            content = log_path.read_bytes()
            log_path.write_bytes(content.replace(secret.encode("utf-8"), b"[REDACTED API KEY]"))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camada", choices=["L0", "L1", "L2", "L4", "L5", "ALL"], default="L0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    layers = "L0,L1,L2,L4,L5" if args.camada == "ALL" else args.camada
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    mutex = api.CreateMutexW(None, True, "Local\\AurenAuthorizedLiveTests")
    if not mutex:
        print("Unable to acquire live-test lock; refusing execution")
        return 125
    if ctypes.get_last_error() == 183:
        api.CloseHandle(mutex)
        print("Another live test is active; refusing overlapping execution")
        return 125
    if args.camada in {"L4", "L5", "ALL"} and not os.environ.get("OPENAI_API_KEY"):
        result = {"reason": "missing_api_key", "exit_code": 125}
    else:
        try:
            result = supervise(
                [sys.executable, "-u", str(root / "testes_auren_live.py"), "--camada", layers],
                cwd=root, log_path=reports / "live.log",
                stop_file=Path(os.environ["USERPROFILE"]) / "auren-remote" / "STOP-LIVE")
        except Exception as exc:
            # Do not serialize arbitrary exceptions/environment containing credentials.
            result = {"reason": "supervisor_error", "exit_code": 125, "error_type": type(exc).__name__}
    result["requested_layers"] = layers
    (reports / "watchdog.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    api.CloseHandle(mutex)
    print(f"Watchdog: {result['reason']}; exit={result['exit_code']}", flush=True)
    return result["exit_code"] if result["exit_code"] in {0, 1, 124, 125, 130} else 1


if __name__ == "__main__":
    raise SystemExit(main())
