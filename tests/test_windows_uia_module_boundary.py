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


def test_windows_uia_starts_persistent_worker_without_bypass(monkeypatch):
    class _Process:
        returncode = None
        stdin = object()
        stdout = object()

    processo = _Process()
    popen_calls = []

    monkeypatch.setattr(windows_uia.os, "name", "nt")
    monkeypatch.setattr(windows_uia._UI_AUTOMATION_WORKER_SCRIPT.__class__, "is_file", lambda _self: True)
    monkeypatch.setattr(windows_uia.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(
        windows_uia.subprocess,
        "Popen",
        lambda *args, **kwargs: popen_calls.append((args, kwargs)) or processo,
    )
    monkeypatch.setattr(
        windows_uia,
        "_UI_AUTOMATION_WORKER",
        None,
    )
    monkeypatch.setattr(
        windows_uia,
        "_UI_AUTOMATION_WORKER_RESPONSES",
        None,
    )

    result, responses = windows_uia._iniciar_ui_automation_worker()

    assert result is processo
    assert responses is not None
    args, kwargs = popen_calls[0]
    assert args[0][-5:] == [
        "-NoProfile",
        "-NonInteractive",
        "-STA",
        "-File",
        str(windows_uia._UI_AUTOMATION_WORKER_SCRIPT),
    ]
    assert "-ExecutionPolicy" not in args[0]
    assert kwargs["stdin"] is windows_uia.subprocess.PIPE
    assert kwargs["stdout"] is windows_uia.subprocess.PIPE
    assert kwargs["stderr"] is windows_uia.subprocess.DEVNULL


def test_windows_uia_reuses_worker_for_multiple_operations(monkeypatch):
    from queue import Queue

    class _Stdin:
        def __init__(self):
            self.writes = []

        def write(self, value):
            self.writes.append(value)
            return len(value)

        def flush(self):
            pass

        def close(self):
            pass

    class _Process:
        returncode = None

        def __init__(self):
            self.stdin = _Stdin()

        def poll(self):
            return None

    processo = _Process()
    respostas = Queue()
    respostas.put({"ok": True, "operacao": "resolver"})
    respostas.put({"ok": True, "operacao": "inspecionar"})
    starts = []

    monkeypatch.setattr(
        windows_uia,
        "_iniciar_ui_automation_worker",
        lambda: starts.append(True) or (processo, respostas),
    )

    primeiro = windows_uia._executar_ui_automation(
        "resolver",
        {"hwnd": 123, "alvo": "Botao"},
    )
    segundo = windows_uia._executar_ui_automation(
        "inspecionar",
        {"hwnd": 123, "foco": "", "max_itens": 5},
    )

    assert primeiro["ok"] is True
    assert segundo["ok"] is True
    assert len(starts) == 2
    assert len(processo.stdin.writes) == 2
