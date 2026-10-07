import tools.windows as windows
import tools.windows_system as windows_system


def test_windows_system_status_lives_in_dedicated_module():
    assert windows._status_windows is windows_system._status_windows
    assert windows.obter_status_windows is windows_system.obter_status_windows
    assert windows._status_windows.__module__ == "tools.windows_system"
    assert windows.obter_status_windows.__module__ == "tools.windows_system"


def test_windows_system_module_owns_system_status_implementation():
    assert hasattr(windows_system, "_status_windows")
    assert hasattr(windows_system, "obter_status_windows")
