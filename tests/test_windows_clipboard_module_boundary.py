import tools.windows as windows
import tools.windows_clipboard as windows_clipboard


def test_windows_clipboard_controls_live_in_dedicated_module():
    assert windows.ler_area_transferencia_windows is windows_clipboard.ler_area_transferencia_windows
    assert windows.definir_area_transferencia_windows is windows_clipboard.definir_area_transferencia_windows
    assert windows.ler_area_transferencia_windows.__module__ == "tools.windows_clipboard"
    assert windows.definir_area_transferencia_windows.__module__ == "tools.windows_clipboard"


def test_windows_module_no_longer_owns_clipboard_backend():
    assert not hasattr(windows, "_configurar_api_clipboard_windows")
    assert hasattr(windows_clipboard, "_configurar_api_clipboard_windows")
