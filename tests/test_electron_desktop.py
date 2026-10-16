"""Testes de contrato do shell Electron (sem GUI real nem chamadas a API)."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ui import chrome_server


ROOT = Path(__file__).resolve().parents[1]
ELECTRON = ROOT / "desktop" / "electron"
MAIN = ELECTRON / "main.cjs"


def test_electron_reuses_original_ui_without_renderer_privileges():
    source = MAIN.read_text(encoding="utf-8")
    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    assert package["main"] == "main.cjs"
    assert package["devDependencies"]["electron"] == "44.7.2"
    assert "nodeIntegration: false" in source
    assert "contextIsolation: true" in source
    assert "sandbox: true" in source
    assert "webSecurity: true" in source
    assert "webviewTag: false" in source
    assert "const parentVenv = path.resolve(root, '..', '.venv', 'Scripts', 'python.exe')" in source
    assert "if (existsSync(parentVenv)) candidates.push" in source
    assert "shell: false" in source
    assert "assets\', \'auren.ico" in source
    assert "icon: existsSync(iconPath) ? iconPath : undefined" in source
    assert "setWindowOpenHandler(() => ({ action: 'deny' }))" in source
    assert "will-navigate" in source
    assert r"127\.0\.0\.1" in source
    assert "'-m', 'ui.chrome_server'" in source
    assert "'--no-browser', '--desktop-stdio'" in source
    assert chrome_server.INDEX_PATH.name == "chrome.html"
    original = chrome_server.INDEX_PATH.read_text(encoding="utf-8")
    assert "THREE.WebGLRenderer" in original
    assert "__AUREN_LOCAL_TOKEN__" in original
    assert "__AUREN_SCRIPT_NONCE__" in original


def test_electron_main_javascript_parses_when_node_installed():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js nao instalado")
    result = subprocess.run(
        [node, "--check", str(MAIN)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr


class StubServer:
    def __init__(self):
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


@pytest.mark.parametrize("payload", [b"", b"mensagem ignorada"])
def test_desktop_stdin_eof_requests_graceful_shutdown(payload):
    server = StubServer()
    chrome_server._watch_desktop_stdin(server, BytesIO(payload))
    assert server.shutdown_calls == 1


def test_desktop_server_starts_and_stops_on_parent_pipe_eof():
    """Subprocesso real sem navegador, mensagens, API ou ferramentas mutaveis."""
    result = subprocess.run(
        [sys.executable, "-u", "-m", "ui.chrome_server", "--no-browser", "--desktop-stdio"],
        input="", capture_output=True, text=True, cwd=ROOT, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Auren Chrome: pagina local." in result.stdout
    assert "Abra: http://127.0.0.1:" in result.stdout


def test_windows_shortcut_points_to_new_shell_without_changing_old_launcher():
    launcher = (ROOT / "scripts" / "iniciar" / "AUREN_DESKTOP.bat").read_text(encoding="utf-8")
    assert "desktop\\electron" in launcher
    assert "npm start" in launcher
    old = (ROOT / "scripts" / "iniciar" / "AUREN_CHROME.bat").read_text(encoding="utf-8")
    assert "-m ui.chrome_server" in old
