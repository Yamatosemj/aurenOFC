"""Testes do canal Chrome local. Sem rede externa, API ou Windows real."""
from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
from queue import Queue
import re
import shutil
import subprocess
from threading import Thread

import pytest

from ui.backend import ConfirmationChoice, UiEvent
from ui.chrome_server import ChromeServer, LocalChromeApp, INDEX_PATH


class FakeWorker:
    def __init__(self) -> None:
        self.events = Queue()
        self.enabled = False
        self.closed = False
        self.messages: list[str] = []
        self.off_calls = 0

    def start(self) -> None:
        pass

    def activate(self) -> None:
        self.enabled = True

    def submit(self, message: str) -> bool:
        if not self.enabled or self.closed:
            return False
        self.messages.append(message)
        return True

    def go_off(self) -> None:
        self.enabled = False
        self.off_calls += 1

    def close(self) -> None:
        self.closed = True


@contextmanager
def running_server():
    fake = FakeWorker()
    app = LocalChromeApp(worker=fake)
    server = ChromeServer(app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, fake, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
        thread.join(timeout=3)


def request(port: int, method: str, path: str, data=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    h = dict(headers or {})
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    try:
        conn.request(method, path, body=body, headers=h)
        res = conn.getresponse()
        content = res.read()
        return res.status, dict(res.getheaders()), content
    finally:
        conn.close()


def auth(app):
    return {"X-Auren-Token": app.token}


def test_starts_off_and_only_submits_when_active():
    with running_server() as (app, worker, port):
        assert app.snapshot()["mode"] == "off"
        status, _, _ = request(port, "POST", "/api/message", {"text": "oi"}, auth(app))
        assert status == 400
        status, _, _ = request(port, "POST", "/api/mode", {"mode": "active"}, auth(app))
        assert status == 200
        status, _, _ = request(port, "POST", "/api/message", {"text": "oi"}, auth(app))
        assert status == 200
        assert worker.messages == ["oi"]
        status, _, _ = request(port, "POST", "/api/message", {"text": "duplo"}, auth(app))
        assert status == 400
        worker.events.put(UiEvent("busy", "Processando..."))
        worker.events.put(UiEvent("reply", "Olá!"))
        worker.events.put(UiEvent("idle"))
        status, _, content = request(port, "GET", "/api/events?after=0", headers=auth(app))
        assert status == 200
        events = json.loads(content)["events"]
        assert [event["kind"] for event in events] == ["you", "busy", "reply", "idle"]
        assert events[-2]["text"] == "Olá!"
        assert app.snapshot()["busy"] is False


def test_standby_disallows_new_messages_and_off_disposes_session():
    with running_server() as (app, worker, port):
        app.change_mode("active")
        app.change_mode("standby")
        status, _, _ = request(port, "POST", "/api/message", {"text": "oi"}, auth(app))
        assert status == 400
        app.change_mode("active")
        app.change_mode("off")
        assert worker.off_calls == 1
        assert app.snapshot()["mode"] == "off"


def test_confirmation_preserves_explicit_approval_and_can_be_denied():
    with running_server() as (app, worker, port):
        app.change_mode("active")
        choice = ConfirmationChoice("Excluir arquivo", "Acao sensivel", "excluir_arquivo")
        worker.events.put(UiEvent("confirm", payload=choice))
        status, _, data = request(port, "GET", "/api/events?after=0", headers=auth(app))
        assert status == 200
        entry = next(e for e in json.loads(data)["events"] if e["kind"] == "confirm")
        assert set(entry["payload"]) == {"id", "action", "reason"}
        status, _, _ = request(
            port, "POST", "/api/confirm",
            {"id": entry["payload"]["id"] + 1, "approved": True}, auth(app),
        )
        assert status == 400
        assert not choice.decided.is_set()
        status, _, _ = request(
            port, "POST", "/api/confirm",
            {"id": entry["payload"]["id"], "approved": False}, auth(app),
        )
        assert status == 200
        assert choice.decided.is_set() and not choice.approved


def test_off_denies_pending_confirmation_and_late_approval():
    with running_server() as (app, worker, port):
        app.change_mode("active")
        choice = ConfirmationChoice("Enviar arquivo", "Envio", "enviar_arquivo")
        worker.events.put(UiEvent("confirm", payload=choice))
        event = next(e for e in app.snapshot()["events"] if e["kind"] == "confirm")
        app.change_mode("off")
        assert choice.decided.is_set() and not choice.approved
        status, _, _ = request(
            port, "POST", "/api/confirm",
            {"id": event["payload"]["id"], "approved": True}, auth(app),
        )
        assert status == 400


def test_local_access_requires_token_and_rejects_cross_origin():
    with running_server() as (app, worker, port):
        status, _, _ = request(port, "POST", "/api/mode", {"mode": "active"})
        assert status == 403
        status, _, _ = request(
            port, "POST", "/api/mode", {"mode": "active"},
            {**auth(app), "Origin": "https://evil.example"},
        )
        assert status == 403
        status, _, _ = request(
            port, "GET", "/", headers={"Host": f"other.example:{port}"},
        )
        assert status == 403
        status, _, _ = request(
            port, "GET", "/", headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert status == 403
        assert app.snapshot()["mode"] == "off"


def test_strict_json_size_schema_and_content_type():
    with running_server() as (app, worker, port):
        status, _, _ = request(
            port, "POST", "/api/mode", {"mode": "active"},
            {**auth(app), "Content-Type": "text/plain"},
        )
        assert status == 415
        status, _, _ = request(port, "POST", "/api/mode", {"mode": "active", "extra": 1}, auth(app))
        assert status == 400
        status, _, _ = request(
            port, "POST", "/api/confirm", {"id": True, "approved": True}, auth(app),
        )
        assert status == 400
        status, _, _ = request(
            port, "POST", "/api/message", {"text": "x" * 5000}, auth(app),
        )
        assert status == 400
        status, _, _ = request(port, "GET", "/api/events?after=oops", headers=auth(app))
        assert status == 400


def test_html_is_prototype_derived_real_ui_and_nonce_is_bound_to_csp():
    source = INDEX_PATH.read_text(encoding="utf-8")
    assert "const E={" in source and '"ouvindo"' in source and '"pensando"' in source
    assert "THREE.WebGLRenderer" in source
    assert "THREE.ShaderMaterial" in source
    assert "THREE.IcosahedronGeometry(1,28)" in source
    assert "const VS=" in source and "const FS=" in source
    assert "getContext(\"2d\"" not in source
    assert 'src="/assets/three-r128.min.js"' in source
    assert "function decide(" not in source
    assert "cdnjs.cloudflare" not in source
    assert "__AUREN_LOCAL_TOKEN__" in source
    assert "__AUREN_SCRIPT_NONCE__" in source
    with running_server() as (app, worker, port):
        status, headers, content = request(port, "GET", "/")
        page = content.decode("utf-8")
        assert status == 200
        assert app.token in page
        assert "__AUREN_SCRIPT_NONCE__" not in page
        assert "__AUREN_LOCAL_TOKEN__" not in page
        nonce = re.search(r'<script nonce="([^"]+)"', page)
        assert nonce is not None
        asset_nonce = re.search(r'<script src="/assets/three-r128.min.js" nonce="([^"]+)"', page)
        assert asset_nonce is not None and asset_nonce.group(1) == nonce.group(1)
        assert f"'nonce-{nonce.group(1)}'" in headers["Content-Security-Policy"]
        assert 'frame-ancestors ' in headers["Content-Security-Policy"]
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Frame-Options"] == "DENY"


def test_browser_script_syntax_if_node_installed():
    """Verifica o JavaScript embutido, sem iniciar Chrome nem chamar API."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node nao instalado neste runner")
    html = INDEX_PATH.read_text(encoding="utf-8")
    scripts = [part for part in re.findall(r"<script[^>]*>([\s\S]*?)</script>", html, re.I) if part.strip()]
    assert len(scripts) == 1
    check = subprocess.run(
        [node, "--check", "-"], input=scripts[0],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert check.returncode == 0, check.stderr



def test_three_js_is_served_locally_without_any_cdn():
    from ui.chrome_server import THREE_SCRIPT_PATH
    assert THREE_SCRIPT_PATH.is_file()
    text = THREE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert text.startswith("/**\n * @license")
    assert "THREE" in text
    assert len(text) > 500_000
    assert (THREE_SCRIPT_PATH.parent / "THREE_LICENSE.txt").is_file()
    with running_server() as (app, worker, port):
        status, headers, content = request(port, "GET", "/assets/three-r128.min.js")
        assert status == 200
        assert headers["Content-Type"].startswith("application/javascript")
        assert content == THREE_SCRIPT_PATH.read_bytes()
        status, _, _ = request(port, "GET", "/assets/../../AUREN_STATE.md")
        assert status == 404


def test_vendor_script_js_syntax_if_node_installed():
    from ui.chrome_server import THREE_SCRIPT_PATH
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node nao instalado")
    check = subprocess.run(
        [node, "--check", "-"],
        input=THREE_SCRIPT_PATH.read_text(encoding="utf-8"),
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert check.returncode == 0, check.stderr
