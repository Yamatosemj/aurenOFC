"""Inoffensive real-process checks for the Windows supervisor; no Auren/UI/API."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from remote_tests.windows_watchdog import supervise


windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects")


def run_fixture(tmp_path, source, **limits):
    script = tmp_path / "fixture.py"
    script.write_text(source, encoding="utf-8")
    return supervise([sys.executable, "-u", script], cwd=tmp_path,
                     log_path=tmp_path / "fixture.log", **limits)


def is_alive(pid):
    import _winapi
    try:
        handle = _winapi.OpenProcess(0x1000 | 0x100000, False, pid)
    except OSError:
        return False
    try:
        return _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
    finally:
        _winapi.CloseHandle(handle)


@windows
def test_success_and_nonzero_exit_are_preserved(tmp_path):
    result = run_fixture(tmp_path, "print('safe fixture')\nraise SystemExit(7)")
    assert result["reason"] == "completed"
    assert result["exit_code"] == 7
    assert "safe fixture" in (tmp_path / "fixture.log").read_text()


@windows
def test_idle_timeout_kills_child_and_grandchild(tmp_path):
    result = run_fixture(tmp_path, """
import subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
Path('grandchild.pid').write_text(str(child.pid))
print('ready', flush=True)
time.sleep(120)
""", idle_seconds=0.8, wall_seconds=5)
    assert result["reason"] == "idle_timeout"
    assert result["exit_code"] == 124
    assert result["duration_seconds"] < 5
    assert not is_alive(result["pid"])
    assert not is_alive(int((tmp_path / "grandchild.pid").read_text()))


@windows
def test_continuous_output_cannot_bypass_wall_timeout(tmp_path):
    result = run_fixture(tmp_path, "import time\nwhile True:\n print('progress', flush=True)\n time.sleep(.03)",
                         wall_seconds=0.8, idle_seconds=5)
    assert result["reason"] == "wall_timeout"
    assert not is_alive(result["pid"])


@windows
def test_log_flood_is_bounded(tmp_path):
    result = run_fixture(tmp_path, "import time\nwhile True:\n print('x'*4096, flush=True)\n time.sleep(.01)",
                         max_log_bytes=8192, wall_seconds=5)
    assert result["reason"] == "log_limit"
    assert (tmp_path / "fixture.log").stat().st_size <= 8192


@windows
def test_stop_file_prevents_test_code_from_running(tmp_path):
    stop = tmp_path / "STOP"
    stop.touch()
    result = run_fixture(tmp_path, "from pathlib import Path; Path('must-not-run').touch()", stop_file=stop)
    assert result["reason"] == "emergency_stop"
    assert result["pid"] is None
    assert not (tmp_path / "must-not-run").exists()


@windows
def test_normal_parent_exit_also_cleans_orphan(tmp_path):
    result = run_fixture(tmp_path, """
import subprocess, sys
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
Path('orphan.pid').write_text(str(child.pid))
""")
    assert result["exit_code"] == 0
    time.sleep(0.1)
    assert not is_alive(int((tmp_path / "orphan.pid").read_text()))


@windows
def test_killing_supervisor_still_kills_its_children(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "supervisor.py"
    script.write_text("""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from remote_tests.windows_watchdog import supervise
source = "import os,time; from pathlib import Path; Path('child.pid').write_text(str(os.getpid())); time.sleep(120)"
supervise([sys.executable, '-c', source], cwd=Path.cwd(), log_path='out.log')
""", encoding="utf-8")
    parent = subprocess.Popen([sys.executable, script, root], cwd=tmp_path)
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "child.pid").exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert (tmp_path / "child.pid").exists()
        pid = int((tmp_path / "child.pid").read_text())
        parent.kill()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5
        while is_alive(pid) and time.monotonic() < deadline:
            time.sleep(.05)
        assert not is_alive(pid)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)


@windows
def test_stdin_file_is_passed_without_interaction(tmp_path):
    source = tmp_path / "commands.txt"
    source.write_text("scripted-input\n")
    result = run_fixture(tmp_path, "print(input())", stdin_path=source)
    assert result["exit_code"] == 0
    assert "scripted-input" in (tmp_path / "fixture.log").read_text()


@windows
def test_key_is_redacted_from_artifact_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret-not-a-real-key")
    result = run_fixture(tmp_path, "import os; print(os.environ['OPENAI_API_KEY'])")
    assert result["exit_code"] == 0
    assert "fixture-secret-not-a-real-key" not in (tmp_path / "fixture.log").read_text()
    assert "[REDACTED API KEY]" in (tmp_path / "fixture.log").read_text()


def test_live_confirmation_does_not_consume_scripted_commands(monkeypatch):
    from core.confirmation import TextConfirmationChannel
    monkeypatch.setenv("AUREN_TEST_MODE", "1")
    channel = TextConfirmationChannel(input_fn=lambda _prompt: pytest.fail("must not read stdin"),
                                      output_fn=lambda _text: None)
    assert channel.confirmar(SimpleNamespace()) is False


def test_live_sdk_timeout_and_retries_without_api(monkeypatch):
    from providers.openai_provider import OpenAIProvider
    captured = []
    monkeypatch.setenv("AUREN_TEST_MODE", "1")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **options: captured.append(options) or object()))
    OpenAIProvider().get_client()
    assert captured == [{"timeout": 45.0, "max_retries": 0}]


def test_normal_sdk_configuration_is_preserved(monkeypatch):
    from providers.openai_provider import OpenAIProvider
    captured = []
    monkeypatch.delenv("AUREN_TEST_MODE", raising=False)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **options: captured.append(options) or object()))
    OpenAIProvider().get_client()
    assert captured == [{}]
