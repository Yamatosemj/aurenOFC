"""Interface local do Auren no Chrome.

Servidor HTTP exclusivo de 127.0.0.1. O navegador e apenas um canal de
texto/confirmacao: nenhuma ferramenta e executada fora do AurenUiWorker.
"""
from __future__ import annotations

import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Empty
import secrets
import shutil
import subprocess
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
import webbrowser

from ui.backend import AurenUiWorker, ConfirmationChoice


INDEX_PATH = Path(__file__).with_name("chrome.html")
MAX_REQUEST_BYTES = 8192
MAX_MESSAGE_CHARS = 4000
MAX_EVENTS = 160


class LocalChromeApp:
    """Gerencia somente a interface, o worker e as confirmacoes de UI."""

    def __init__(self, worker: AurenUiWorker | None = None) -> None:
        self.worker = worker or AurenUiWorker()
        self.mode = "off"
        self.busy = False
        self.token = secrets.token_urlsafe(36)
        self.lock = Lock()
        self.counter = 0
        self.history: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self.pending: tuple[int, ConfirmationChoice] | None = None
        self.worker.start()

    def _push(self, kind: str, text: str = "", payload: dict[str, Any] | None = None) -> None:
        self.counter += 1
        self.history.append({
            "seq": self.counter,
            "kind": kind,
            "text": text,
            "payload": payload or {},
        })

    def _drain(self) -> None:
        """Chamado com lock. Remove objetos Python do payload enviado ao navegador."""
        while True:
            try:
                event = self.worker.events.get_nowait()
            except Empty:
                break
            if event.kind == "confirm":
                choice = event.payload
                if not isinstance(choice, ConfirmationChoice):
                    continue
                self.counter += 1
                request_id = self.counter
                self.pending = (request_id, choice)
                self.history.append({
                    "seq": request_id,
                    "kind": "confirm",
                    "text": "",
                    "payload": {
                        "id": request_id,
                        "action": choice.action[:600],
                        "reason": choice.reason[:1200],
                    },
                })
                continue
            if event.kind == "confirm_done":
                if self.pending is not None and self.pending[1] is event.payload:
                    self.pending = None
            if event.kind == "busy":
                self.busy = True
            if event.kind == "idle":
                self.busy = False
            if event.kind == "closed":
                self.mode = "off"
                self.busy = False
            self._push(event.kind, str(event.text or "")[:10000])

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        with self.lock:
            self._drain()
            after = max(0, after)
            # Caso o navegador tenha perdido eventos, notificar da lacuna.
            gap = bool(self.history and after and after < self.history[0]["seq"] - 1)
            items = [item for item in self.history if item["seq"] > after]
            return {
                "mode": self.mode,
                "busy": self.busy,
                "seq": self.counter,
                "gap": gap,
                "events": items,
            }

    def change_mode(self, mode: str) -> dict[str, Any]:
        with self.lock:
            self._drain()
            if mode == "active":
                self.worker.activate()
                self.mode = "active"
            elif mode == "standby":
                if self.mode == "off":
                    raise ValueError("Ative o Auren antes de entrar em standby.")
                self.mode = "standby"
            elif mode == "off":
                self.worker.go_off()
                self.mode = "off"
                self.busy = False
                if self.pending is not None:
                    self.pending[1].answer(False)
                    self.pending = None
            else:
                raise ValueError("Modo desconhecido.")
            return {"mode": self.mode}

    def submit(self, message: str) -> dict[str, Any]:
        if not isinstance(message, str):
            raise ValueError("A mensagem deve ser texto.")
        message = message.strip()
        if not message or len(message) > MAX_MESSAGE_CHARS:
            raise ValueError("Envie uma mensagem entre 1 e 4000 caracteres.")
        with self.lock:
            self._drain()
            if self.mode != "active" or self.busy:
                raise ValueError("Ative o Auren e aguarde a tarefa atual terminar.")
            if not self.worker.submit(message):
                raise ValueError("O Auren nao aceitou a mensagem.")
            self.busy = True
            self._push("you", message)
            return {"accepted": True}

    def confirm(self, request_id: int, approved: bool) -> dict[str, Any]:
        with self.lock:
            self._drain()
            if self.pending is None or self.pending[0] != request_id:
                raise ValueError("Esta confirmacao nao esta mais pendente.")
            choice = self.pending[1]
            if choice.decided.is_set():
                self.pending = None
                raise ValueError("Esta confirmacao ja foi encerrada.")
            choice.answer(bool(approved) and self.mode == "active")
            self.pending = None
            return {"recorded": True}

    def shutdown(self) -> None:
        with self.lock:
            if self.pending is not None:
                self.pending[1].answer(False)
                self.pending = None
        self.worker.close()


class ChromeRequestHandler(BaseHTTPRequestHandler):
    server: "ChromeServer"
    server_version = "AurenChrome/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        # Nao registre URLs/tokens/comandos dos usuarios nos logs HTTP.
        return

    def _secure(self) -> bool:
        host = self.headers.get("Host", "")
        expected = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        return (
            self.client_address[0] == "127.0.0.1"
            and host == expected
            and (origin is None or origin == f"http://{expected}")
            and fetch_site not in {"cross-site", "same-site"}
        )

    def _headers(self, code: int, mime: str, size: int) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'nonce-" + getattr(self, "_page_nonce", "") + "'; "
            "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
            "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()

    def _bytes(self, code: int, content: bytes, mime: str = "application/json; charset=utf-8") -> None:
        self._headers(code, mime, len(content))
        self.wfile.write(content)

    def _json(self, code: int, data: dict[str, Any]) -> None:
        self._bytes(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _bad(self, code: int, message: str) -> None:
        self._json(code, {"error": message})

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Auren-Token", ""), self.server.app.token)

    def do_GET(self) -> None:
        if not self._secure():
            self._bad(403, "Acesso local negado.")
            return
        path = urlsplit(self.path).path
        if path == "/":
            self._page_nonce = secrets.token_urlsafe(24)
            html = INDEX_PATH.read_text(encoding="utf-8")
            html = html.replace("__AUREN_SCRIPT_NONCE__", self._page_nonce)
            html = html.replace(
                "__AUREN_LOCAL_TOKEN__",
                json.dumps(self.server.app.token)[1:-1],
            )
            self._bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/events":
            if not self._authorized():
                self._bad(403, "Sessao nao autorizada.")
                return
            try:
                after = int(urlsplit(self.path).query.removeprefix("after="))
            except ValueError:
                self._bad(400, "Sequencia invalida.")
                return
            self._json(200, self.server.app.snapshot(after))
            return
        self._bad(404, "Rota inexistente.")

    def do_POST(self) -> None:
        if not self._secure() or not self._authorized():
            self._bad(403, "Sessao nao autorizada.")
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._bad(415, "Somente JSON e aceito.")
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if not (0 <= length <= MAX_REQUEST_BYTES):
            self._bad(413, "Tamanho de requisicao invalido.")
            return
        try:
            obj = json.loads(self.rfile.read(length))
            if not isinstance(obj, dict):
                raise ValueError("O corpo precisa ser um objeto JSON.")
            path = urlsplit(self.path).path
            if path == "/api/mode":
                if set(obj) != {"mode"} or not isinstance(obj["mode"], str):
                    raise ValueError("Modo invalido.")
                result = self.server.app.change_mode(obj["mode"])
            elif path == "/api/message":
                if set(obj) != {"text"}:
                    raise ValueError("Mensagem invalida.")
                result = self.server.app.submit(obj["text"])
            elif path == "/api/confirm":
                if (
                    set(obj) != {"id", "approved"}
                    or type(obj["id"]) is not int
                    or type(obj["approved"]) is not bool
                ):
                    raise ValueError("Confirmacao invalida.")
                result = self.server.app.confirm(obj["id"], obj["approved"])
            else:
                self._bad(404, "Rota inexistente.")
                return
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self._bad(400, str(exc))
            return
        self._json(200, result)


class ChromeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, app: LocalChromeApp, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), ChromeRequestHandler)
        self.app = app


def _open_chrome(url: str) -> None:
    candidates = [shutil.which("chrome"), shutil.which("chrome.exe")]
    if os.name == "nt":
        for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            folder = os.environ.get(name)
            if folder:
                candidates.append(str(Path(folder) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            subprocess.Popen([candidate, "--new-window", url], shell=False)
            return
    webbrowser.open(url, new=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interface local do Auren no Chrome.")
    parser.add_argument("--port", type=int, default=0, help="Porta local (padrao: livre automaticamente).")
    parser.add_argument("--no-browser", action="store_true", help="Nao abrir navegador automaticamente.")
    args = parser.parse_args()
    app = LocalChromeApp()
    try:
        with ChromeServer(app, args.port) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print("Auren Chrome: pagina local. Nao acessivel pela rede.")
            print(f"Abra: {url}")
            print("Feche com Ctrl+C nesta janela para encerrar o servidor.")
            if not args.no_browser:
                _open_chrome(url)
            server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
