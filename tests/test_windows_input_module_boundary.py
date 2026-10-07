import tools.windows as windows
import tools.windows_input as windows_input


def test_windows_input_controls_live_in_dedicated_module():
    public_names = (
        "controle_midia_windows",
        "pressionar_tecla_windows",
        "mover_mouse_windows",
        "clicar_mouse_windows",
        "arrastar_mouse_windows",
    )

    for name in public_names:
        assert getattr(windows, name) is getattr(windows_input, name)
        assert getattr(windows, name).__module__ == "tools.windows_input"


def test_windows_input_module_owns_keyboard_backend():
    assert windows._pressionar_vk is windows_input._pressionar_vk
    assert windows._pressionar_vk.__module__ == "tools.windows_input"


def test_windows_module_reexports_input_dpi_helpers_used_by_screen_capture():
    assert windows._contexto_dpi_per_monitor_windows is windows_input._contexto_dpi_per_monitor_windows
    assert windows._limites_tela_virtual_windows is windows_input._limites_tela_virtual_windows
