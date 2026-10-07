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
