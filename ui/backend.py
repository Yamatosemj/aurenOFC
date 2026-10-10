"""Ponte entre interface desktop e o Harness V47.

Nenhuma ferramenta executa fora do Router/Dispatcher. Nenhuma chamada Tk ocorre
nas threads de trabalho; resultados e confirmacoes trafegam por Queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Callable


@dataclass
class UiEvent:
    kind: str
    text: str = ""
    payload: Any = None


@dataclass
class ConfirmationChoice:
    action: str
    reason: str
    tool_name: str
    decided: Event = field(default_factory=Event)
    approved: bool = False

    def answer(self, approve: bool) -> None:
        if not self.decided.is_set():
            self.approved = bool(approve)
            self.decided.set()


class GuiConfirmationChannel:
    """Solicita aprovacao na UI; timeout/fechamento sempre negam a acao."""

    def __init__(
        self,
        events: Queue[UiEvent],
        register_pending: Callable[[ConfirmationChoice | None], None],
        *,
        timeout: float = 45.0,
    ) -> None:
        self.events = events
        self.register_pending = register_pending
        self.timeout = timeout

    def confirmar(self, request: Any) -> bool:
        choice = ConfirmationChoice(
            action=str(request.action),
            reason=str(request.reason),
            tool_name=str(request.tool_name),
        )
        self.register_pending(choice)
        self.events.put(UiEvent("confirm", payload=choice))
        try:
            if not choice.decided.wait(self.timeout):
                choice.answer(False)
                self.events.put(UiEvent("notice", "Confirmacao expirada. Acao negada."))
            return bool(choice.approved)
        finally:
            self.register_pending(None)
            self.events.put(UiEvent("confirm_done", payload=choice))


class AurenUiWorker:
    """Serializa tarefas em uma thread e mantém uma unica sessao do Harness."""

    def __init__(self, harness_factory: Callable[..., Any] | None = None) -> None:
        self.events: Queue[UiEvent] = Queue()
        self._requests: Queue[tuple[str, str, int]] = Queue()
        self._harness_factory = harness_factory
        self._harness: Any = None
        self._pending: ConfirmationChoice | None = None
        self._lock = Lock()
        self._enabled = False
        self._generation = 0
        self._closing = Event()
        self._thread = Thread(target=self._run, name="auren-ui-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def activate(self) -> None:
        with self._lock:
            if not self._closing.is_set():
                self._enabled = True

    def submit(self, text: str) -> bool:
        text = str(text or "").strip()
        with self._lock:
            if not text or self._closing.is_set() or not self._enabled:
                return False
            generation = self._generation
        self._requests.put(("message", text, generation))
        return True

    def _set_pending(self, choice: ConfirmationChoice | None) -> None:
        with self._lock:
            self._pending = choice

    def deny_pending(self) -> None:
        with self._lock:
            choice = self._pending
        if choice is not None:
            choice.answer(False)

    def cancel_current(self) -> None:
        self.deny_pending()
        with self._lock:
            harness = self._harness
        if harness is not None:
            try:
                harness.cancel_current_task()
            except Exception:
                pass

    def go_off(self) -> None:
        if self._closing.is_set():
            return
        with self._lock:
            self._enabled = False
            self._generation += 1
            generation = self._generation
        self.cancel_current()
        self._requests.put(("off", "", generation))

    def close(self) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        with self._lock:
            self._enabled = False
            self._generation += 1
            generation = self._generation
        self.cancel_current()
        self._requests.put(("quit", "", generation))

    def _make_harness(self) -> Any:
        channel = GuiConfirmationChannel(self.events, self._set_pending)
        if self._harness_factory is not None:
            return self._harness_factory(confirmation_channel=channel)
        # Import tardio: abrir a janela nao conecta a API nem inicia a voz.
        import auren
        return auren.criar_harness(confirmation_channel=channel)

    def _dispose_harness(self) -> None:
        with self._lock:
            harness, self._harness = self._harness, None
        if harness is None:
            return
        # Mesma finalizacao de executar() no Harness, sem duplicar executores.
        try:
            bg = getattr(harness, "_background_queue", None)
            if bg is not None:
                bg.shutdown(cancel_pending=False)
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao encerrar tarefas: {exc}"))
        try:
            harness.fechar()
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao fechar navegador: {exc}"))
        try:
            harness._encerrar_sessao_chat("closed")
        except Exception as exc:
            self.events.put(UiEvent("notice", f"Aviso ao fechar sessao: {exc}"))

    def _run(self) -> None:
        try:
            while True:
                operation, text, generation = self._requests.get()
                if operation == "quit" or self._closing.is_set():
                    break
                if operation == "off":
                    self._dispose_harness()
                    self.events.put(UiEvent("off"))
                    continue
                if operation != "message":
                    continue
                with self._lock:
                    valid = self._enabled and generation == self._generation
                if not valid:
                    continue

                self.events.put(UiEvent("busy", "Processando..."))
                try:
                    with self._lock:
                        harness = self._harness
                    if harness is None:
                        harness = self._make_harness()
                        with self._lock:
                            self._harness = harness
                    with self._lock:
                        still_valid = self._enabled and generation == self._generation
                    if not still_valid or self._closing.is_set():
                        continue
                    quick, response = harness.processar_mensagem(text)
                    answer = response if quick else getattr(response, "output_text", str(response))
                    answer = str(answer or "").strip() or "(Sem resposta textual.)"
                    snapshot = harness.current_task()
                    status = getattr(getattr(snapshot, "state", None), "value", "")
                    if status == "failed":
                        self.events.put(UiEvent("error", answer))
                    else:
                        self.events.put(UiEvent("reply", answer))
                except Exception as exc:
                    self.events.put(UiEvent("error", f"Erro ao processar: {exc}"))
                finally:
                    self.events.put(UiEvent("idle"))
        finally:
            self.deny_pending()
            self._dispose_harness()
            self.events.put(UiEvent("closed"))
