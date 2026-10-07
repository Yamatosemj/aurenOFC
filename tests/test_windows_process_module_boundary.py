import tools.windows as windows
import tools.windows_processes as windows_processes


def test_windows_process_controls_live_in_dedicated_module():
    assert windows.listar_processos_windows is windows_processes.listar_processos_windows
    assert windows.encerrar_processo_windows is windows_processes.encerrar_processo_windows
    assert windows._nome_executavel_por_pid_windows is windows_processes._nome_executavel_por_pid_windows


def test_windows_module_no_longer_owns_process_implementations():
    assert "def listar_processos_windows(" not in windows.listar_processos_windows.__code__.co_filename
    assert "windows_processes" in windows.listar_processos_windows.__module__
    assert "windows_processes" in windows.encerrar_processo_windows.__module__
