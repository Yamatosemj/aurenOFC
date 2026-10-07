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
    assert hasattr(windows_uia, "_UI_AUTOMATION_POWERSHELL")
    assert not hasattr(windows, "_UI_AUTOMATION_POWERSHELL")


def test_windows_uia_reuses_window_resolution_boundary():
    assert windows_uia._encontrar_janela_windows.__module__ == "tools.windows_window"
