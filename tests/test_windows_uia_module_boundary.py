import tools.windows as windows
import tools.windows_uia as windows_uia


def test_windows_uia_public_controls_live_in_dedicated_module():
    public_names = (
        "inspecionar_interface_windows",
        "clicar_elemento_windows",
        "preencher_elemento_windows",
        "alternar_elemento_windows",
        "selecionar_elemento_windows",
    )

    for name in public_names:
        assert getattr(windows, name) is getattr(windows_uia, name)
        assert getattr(windows, name).__module__ == "tools.windows_uia"


def test_windows_uia_execution_helpers_live_in_dedicated_module():
    assert windows._executar_ui_automation is windows_uia._executar_ui_automation
    assert windows._executar_ui_automation.__module__ == "tools.windows_uia"
    assert windows._ui_automation_janela is windows_uia._ui_automation_janela
    assert windows._ui_automation_janela.__module__ == "tools.windows_uia"
    assert windows_uia._UI_AUTOMATION_WORKER_SCRIPT.name == "windows_uia_worker.ps1"
    assert not hasattr(windows, "_UI_AUTOMATION_WORKER_SCRIPT")


def test_windows_uia_reuses_window_resolution_boundary():
    assert windows_uia._encontrar_janela_windows.__module__ == "tools.windows_window"


def test_windows_uia_reuses_persistent_worker_over_stdin_stdout(monkeypatch):
    calls = []

    class _Stdin:
        def write(self, value):
            calls.append(("write", value))
            return len(value)

        def flush(self):
            calls.append(("flush", None))

        def close(self):
            calls.append(("close", None))

    class _Stdout:
        def __iter__(self):
            return iter([
                '{"ok":true,"operacao":"resolver"}\n',
                '{"ok":true,"operacao":"inspecionar"}\n',
            ])

    class _Process:
        def __init__(self):
            self.returncode = None
            self.stdin = _Stdin()
            self.stdout = _Stdout()

        def poll(self):
            return None

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.returncode = -9

    processo = _Process()
    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return processo

    monkeypatch.setattr(windows_uia.os, "name", "nt")
    monkeypatch.setattr(windows_uia.shutil, "which", lambda name: "powershell.exe")
    monkeypatch.setattr(windows_uia.subprocess, "Popen", fake_popen)
    windows_uia._encerrar_ui_automation_worker()

    primeiro = windows_uia._executar_ui_automation(
        "resolver",
        {"hwnd": 123, "alvo": "Botao"},
    )
    segundo = windows_uia._executar_ui_automation(
        "inspecionar",
        {"hwnd": 123, "foco": "", "max_itens": 5},
    )

    try:
        assert primeiro["ok"] is True
        assert segundo["ok"] is True
        assert len(popen_calls) == 1
        args, kwargs = popen_calls[0]
        assert args[0][-5:] == ["-NoProfile", "-NonInteractive", "-STA", "-File", str(windows_uia._UI_AUTOMATION_WORKER_SCRIPT)]
        assert "-ExecutionPolicy" not in args[0]
        assert kwargs["stdin"] is windows_uia.subprocess.PIPE
        assert kwargs["stdout"] is windows_uia.subprocess.PIPE
        assert kwargs["stderr"] is windows_uia.subprocess.DEVNULL
        assert sum(1 for item in calls if item[0] == "write") == 2
    finally:
        windows_uia._encerrar_ui_automation_worker()
