import tools.windows as windows
import tools.windows_screenshot as windows_screenshot


def test_windows_screenshot_lives_in_dedicated_module():
    assert windows.capturar_tela_windows is windows_screenshot.capturar_tela_windows
    assert windows.capturar_tela_windows.__module__ == "tools.windows_screenshot"


def test_windows_screenshot_module_owns_capture_implementation():
    assert hasattr(windows_screenshot, "capturar_tela_windows")
