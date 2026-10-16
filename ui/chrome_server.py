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
import sys
from threading import Lock, Thread
from time import monotonic
from typing import Any, BinaryIO
from urllib.parse import urlsplit, parse_qs
import webbrowser

from ui.backend import AurenUiWorker, ConfirmationChoice
from ui.conversation_history import UiConversationHistory, MAX_SEARCH, MAX_TEXT


INDEX_PATH = Path(__file__).with_name("chrome.html")
THREE_SCRIPT_PATH = Path(__file__).resolve().parent / "vendor" / "three-r128.min.js"
MAX_REQUEST_BYTES = 8192
MAX_MESSAGE_CHARS = 4000
MAX_EVENTS = 160
STANDBY_AFTER_SECONDS = 120
EXIT_COMMANDS = {"sair", "desligar auren", "desligue auren", "encerrar auren", "fechar auren"}


class LocalChromeApp:
    """Gerencia somente a interface, o worker e as confirmacoes de UI."""

    def __init__(self, worker: AurenUiWorker | None = None, history_store: UiConversationHistory | None = None) -> None:
        self.worker = worker or AurenUiWorker()
        self.history_store = history_store or UiConversationHistory()
        self.active_chat_id: str | None = None
        self.mode = "off"
        self.busy = False
        self.last_activity = monotonic()
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
            # Os eventos podem ter sido emitidos antes de Desligar/reativar.
            # Nao deixar idle/off/confirm de uma sessao anterior afetar a atual.
            event_generation = getattr(event, "generation", None)
            worker_generation = getattr(self.worker, "generation", None)
            if event_generation is not None and event_generation != worker_generation:
                if event.kind == "confirm" and isinstance(event.payload, ConfirmationChoice):
                    event.payload.answer(False)
                continue
            # Persistir SOMENTE depois de validar a geracao da sessao.
            # Resposta obsoleta nao pertence ao chat reativado.
            if event.kind in {"reply", "error"} and self.active_chat_id:
                try:
                    if isinstance(event.payload, dict):
                        source_id = event.payload.get("source_chat_id")
                        if isinstance(source_id, str):
                            self.history_store.bind_harness_chat(self.active_chat_id, source_id)
                    self.history_store.append(
                        self.active_chat_id,
                        "assistant" if event.kind == "reply" else "error",
                        str(event.text or "")[:MAX_TEXT],
                    )
                except Exception:
                    # Nao incluir conteudo da mensagem no erro da UI.
                    self._push("notice", "Nao foi possivel salvar uma resposta no historico.")
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
                self.last_activity = monotonic()
            if event.kind == "closed":
                self.mode = "off"
                self.busy = False
            self._push(event.kind, str(event.text or "")[:10000])

    def _maybe_standby(self) -> None:
        """Chamado com lock: nunca interrompe tarefa ou confirmação pendente."""
        if (
            self.mode == "active"
            and not self.busy
            and self.pending is None
            and monotonic() - self.last_activity >= STANDBY_AFTER_SECONDS
        ):
            self.mode = "standby"

    def _go_off(self) -> None:
        """Chamado com lock: encerra a sessão sem finalizar o servidor local."""
        self.worker.go_off()
        self.mode = "off"
        self.busy = False
        if self.pending is not None:
            self.pending[1].answer(False)
            self.pending = None

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        with self.lock:
            self._drain()
            self._maybe_standby()
            after = max(0, after)
            # Caso o navegador tenha perdido eventos, notificar da lacuna.
            gap = bool(self.history and after and after < self.history[0]["seq"] - 1)
            items = [item for item in self.history if item["seq"] > after]
            return {
                "mode": self.mode,
                "busy": self.busy,
                "active_chat_id": self.active_chat_id,
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
                self.last_activity = monotonic()
            elif mode == "standby":
                if self.mode == "off":
                    raise ValueError("Ative o Auren antes de entrar em standby.")
                self.mode = "standby"
            elif mode == "off":
                self._go_off()
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
            self._maybe_standby()
            if message.casefold().strip(" .!?") in EXIT_COMMANDS:
                self._push("you", message)
                if self.mode != "off":
                    self._go_off()
                self.active_chat_id = None
                return {"accepted": True, "mode": "off"}
            if self.busy:
                raise ValueError("Aguarde a tarefa atual terminar.")
            # Qualquer mensagem comum acorda o Auren sem seleção manual.
            if self.mode != "active":
                self.worker.activate()
                self.mode = "active"
            if not self.worker.submit(message):
                raise ValueError("O Auren nao aceitou a mensagem.")
            self.busy = True
            self.last_activity = monotonic()
            try:
                if self.active_chat_id is None:
                    self.active_chat_id = self.history_store.create_chat()
                self.history_store.append(self.active_chat_id, "user", message)
            except Exception:
                self._push("notice", "Mensagem enviada, mas nao foi salva no historico.")
            self._push("you", message)
            return {"accepted": True, "mode": self.mode}

    def new_chat(self) -> dict[str, Any]:
        """Troca somente a sessao da UI e solicita descarte do Harness anterior."""
        with self.lock:
            self._drain()
            if self.busy or self.pending is not None:
                raise ValueError("Aguarde a tarefa ou confirmacao atual terminar.")
            self._go_off()
            self.active_chat_id = None
            self._push("new_chat")
            return {"active_chat_id": None, "mode": "off"}

    def list_chats(self, query: str) -> dict[str, Any]:
        return {"chats": self.history_store.list_chats(query), "active_chat_id": self.active_chat_id}

    def read_chat(self, chat_id: str, after: int) -> dict[str, Any]:
        return self.history_store.get_messages(chat_id, after=after)

    def read_technical_log(self, chat_id: str) -> dict[str, str]:
        return {"text": self.history_store.technical_log(chat_id)}

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
        if path == "/assets/three-r128.min.js":
            # Dependencia WebGL fixa: nunca expor caminhos arbitrarios do projeto.
            self._bytes(
                200,
                THREE_SCRIPT_PATH.read_bytes(),
                "application/javascript; charset=utf-8",
            )
            return
        if path == "/api/history" or path.startswith("/api/history/"):
            if not self._authorized():
                self._bad(403, "Sessao nao autorizada.")
                return
            try:
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if path.endswith("/technical-log") and path.startswith("/api/history/"):
                    if params:
                        raise ValueError("Consulta de log invalida.")
                    chat_id = path.removeprefix("/api/history/").removesuffix("/technical-log")
                    if "/" in chat_id:
                        raise ValueError("Identificador de conversa invalido.")
                    result = self.server.app.read_technical_log(chat_id)
                elif path == "/api/history":
                    if set(params) - {"q"} or len(params.get("q", [""])) != 1:
                        raise ValueError("Pesquisa invalida.")
                    query = params.get("q", [""])[0]
                    if len(query) > MAX_SEARCH:
                        raise ValueError("Pesquisa muito longa.")
                    result = self.server.app.list_chats(query)
                else:
                    if set(params) - {"after"} or len(params.get("after", ["0"])) != 1:
                        raise ValueError("Cursor invalido.")
                    result = self.server.app.read_chat(
                        path.removeprefix("/api/history/"),
                        int(params.get("after", ["0"])[0]),
                    )
            except (ValueError, TypeError) as exc:
                message = str(exc) if path.endswith("/technical-log") else "Consulta de historico invalida."
                self._bad(400, message)
                return
            self._json(200, result)
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
            if path == "/api/history/new":
                if obj:
                    raise ValueError("Nova conversa nao aceita parametros.")
                result = self.server.app.new_chat()
            elif path == "/api/mode":
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


def _watch_desktop_stdin(server: ChromeServer, source: BinaryIO) -> None:
    """Encerra o HTTP ao receber EOF do processo Electron (sem navegador externo)."""
    try:
        while source.read(1024):
            pass
    except (OSError, ValueError):
        pass
    server.shutdown()


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
    parser.add_argument("--desktop-stdio", action="store_true", help="Encerrar ao receber EOF do aplicativo desktop.")
    args = parser.parse_args()
    app = LocalChromeApp()
    try:
        with ChromeServer(app, args.port) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print("Auren Chrome: pagina local. Nao acessivel pela rede.")
            print(f"Abra: {url}")
            print("Feche com Ctrl+C nesta janela para encerrar o servidor.")
            if args.desktop_stdio:
                Thread(
                    target=_watch_desktop_stdin,
                    args=(server, sys.stdin.buffer),
                    name="auren-desktop-stdin",
                    daemon=True,
                ).start()
            if not args.no_browser:
                _open_chrome(url)
            server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
