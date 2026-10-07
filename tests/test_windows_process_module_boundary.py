import tools.windows as windows
import tools.windows_processes as windows_processes


def test_windows_process_controls_live_in_dedicated_module():
    assert windows.listar_processos_windows is windows_processes.listar_processos_windows
    assert windows.encerrar_processo_windows is windows_processes.encerrar_processo_windows
    assert windows._nome_executavel_por_pid_windows is windows_processes._nome_executavel_por_pid_windows
    assert windows.listar_processos_windows.__module__ == "tools.windows_processes"
    assert windows.encerrar_processo_windows.__module__ == "tools.windows_processes"
    assert windows._nome_executavel_por_pid_windows.__module__ == "tools.windows_processes"


def test_windows_process_module_owns_process_implementation():
    assert hasattr(windows_processes, "_nome_executavel_por_pid_windows")
    assert hasattr(windows_processes, "listar_processos_windows")
    assert hasattr(windows_processes, "encerrar_processo_windows")


def test_windows_process_name_resolution_rejects_multiple_pids(monkeypatch):
    import io
    import csv

    class _Result:
        returncode = 0
        stdout = '"chrome.exe","1111","Console","1","100 MB"\n"chrome.exe","2222","Console","1","100 MB"\n'
        stderr = ""

    monkeypatch.setattr(windows_processes.os, "name", "nt")
    monkeypatch.setattr(
        windows_processes.subprocess,
        "run",
        lambda *_args, **_kwargs: _Result(),
    )

    result = windows_processes.encerrar_processo_windows(nome="chrome.exe")

    assert result.ok is False
    assert result.error_code == "process_name_ambiguous"
    assert result.data["pids"] == [1111, 2222]


def test_windows_security_process_names_are_protected(monkeypatch):
    monkeypatch.setattr(windows_processes.os, "name", "nt")
    monkeypatch.setattr(
        windows_processes,
        "_nome_executavel_por_pid_windows",
        lambda _pid: "msmpeng.exe",
    )

    result = windows_processes.encerrar_processo_windows(pid=1234)

    assert result.ok is False
    assert "protegido" in result.message.lower()
