import tools.windows as windows
import tools.windows_screenshot as windows_screenshot


def test_windows_screenshot_lives_in_dedicated_module():
    assert windows.capturar_tela_windows is windows_screenshot.capturar_tela_windows
    assert windows.capturar_tela_windows.__module__ == "tools.windows_screenshot"


def test_windows_screenshot_module_owns_capture_implementation():
    assert hasattr(windows_screenshot, "capturar_tela_windows")


def test_windows_screenshot_cleanup_removes_old_and_excess_files(tmp_path, monkeypatch):
    import time
    from pathlib import Path

    monkeypatch.setattr(windows_screenshot, "SCREENSHOT_MAX_FILES", 2)
    monkeypatch.setattr(windows_screenshot, "SCREENSHOT_MAX_TOTAL_BYTES", 12)

    oldest = Path(tmp_path) / "screen_1.png"
    middle = Path(tmp_path) / "screen_2.png"
    newest = Path(tmp_path) / "screen_3.png"
    oldest.write_bytes(b"123456")
    middle.write_bytes(b"123456")
    newest.write_bytes(b"123456")
    now = time.time()
    import os
    os.utime(oldest, (now - 10 * 86400, now - 10 * 86400))

    windows_screenshot._limpar_screenshots(Path(tmp_path))

    assert not oldest.exists()
    remaining = sorted(p.name for p in Path(tmp_path).glob("screen_*.png"))
    assert len(remaining) <= 2
    assert sum(p.stat().st_size for p in Path(tmp_path).glob("screen_*.png")) <= 12
