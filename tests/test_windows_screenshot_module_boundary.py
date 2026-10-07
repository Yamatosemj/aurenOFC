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


def test_screenshot_cleanup_removes_old_files_and_respects_limits(tmp_path, monkeypatch):
    old = tmp_path / "screen_old.png"
    recent = tmp_path / "screen_recent.png"
    old.write_bytes(b"old")
    recent.write_bytes(b"recent")

    old_ts = windows_screenshot.datetime.now().timestamp() - (
        (windows_screenshot.SCREENSHOT_RETENTION_DAYS + 1) * 86400
    )
    import os
    os.utime(old, (old_ts, old_ts))

    monkeypatch.setattr(windows_screenshot, "SCREENSHOT_MAX_FILES", 1)
    windows_screenshot._limpar_screenshots(tmp_path)

    assert not old.exists()
    assert recent.exists()


def test_screenshot_cleanup_deletes_oldest_when_file_count_exceeds_limit(tmp_path, monkeypatch):
    import os
    arquivos = []
    for index in range(3):
        path = tmp_path / f"screen_{index}.png"
        path.write_bytes(b"x" * 10)
        timestamp = windows_screenshot.datetime.now().timestamp() + index
        os.utime(path, (timestamp, timestamp))
        arquivos.append(path)

    monkeypatch.setattr(windows_screenshot, "SCREENSHOT_RETENTION_DAYS", 999)
    monkeypatch.setattr(windows_screenshot, "SCREENSHOT_MAX_FILES", 2)
    windows_screenshot._limpar_screenshots(tmp_path)

    assert not arquivos[0].exists()
    assert arquivos[1].exists()
    assert arquivos[2].exists()
