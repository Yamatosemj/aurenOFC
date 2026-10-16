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
    generation: int | None = None


@dataclass
class ConfirmationChoice:
    action: str
    reason: str
    tool_name: str
    decided: Event = field(default_factory=Event)
    approved: bool = False
    _answer_lock: Lock = field(default_factory=Lock, repr=False)

    def answer(self, approve: bool) -> None:
        # A interface e o cancelamento podem responder em threads diferentes.
        with self._answer_lock:
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
        generation: int | None = None,
        is_current: Callable[[], bool] | None = None,
    ) -> None:
        self.events = events
        self.register_pending = register_pending
        self.timeout = timeout
        self.generation = generation
        self.is_current = is_current

    def confirmar(self, request: Any) -> bool:
        choice = ConfirmationChoice(
            action=str(request.action),
            reason=str(request.reason),
            tool_name=str(request.tool_name),
        )
        self.register_pending(choice)
        try:
            # Cancelamento/Desligado pode ocorrer antes da publicacao do modal.
            # Nao deixar uma confirmacao antiga esperando 45 s ou ser aprovada.
            if self.is_current is not None and not self.is_current():
                choice.answer(False)
                return False
            if choice.decided.is_set():
                return False
            self.events.put(UiEvent("confirm", payload=choice, generation=self.generation))
            if not choice.decided.wait(self.timeout):
                choice.answer(False)
                self.events.put(UiEvent("notice", "Confirmacao expirada. Acao negada.", generation=self.generation))
            return bool(choice.approved)
        finally:
            self.register_pending(None)
            self.events.put(UiEvent("confirm_done", payload=choice, generation=self.generation))


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

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def _generation_is_active(self, generation: int) -> bool:
        with self._lock:
            return self._enabled and generation == self._generation and not self._closing.is_set()

    def activate(self) -> None:
        with self._lock:
            if not self._closing.is_set():
                if not self._enabled:
                    # Reativar invalida o "off" ainda aguardando no worker.
                    self._generation += 1
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

    def _make_harness(self, generation: int) -> Any:
        channel = GuiConfirmationChannel(
            self.events, self._set_pending,
            generation=generation,
            is_current=lambda: self._generation_is_active(generation),
        )
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
                    self.events.put(UiEvent("off", generation=generation))
                    continue
                if operation != "message":
                    continue
                with self._lock:
                    valid = self._enabled and generation == self._generation
                if not valid:
                    continue

                self.events.put(UiEvent("busy", "Processando...", generation=generation))
                try:
                    with self._lock:
                        harness = self._harness
                    if harness is None:
                        harness = self._make_harness(generation)
                        with self._lock:
                            self._harness = harness
                    with self._lock:
                        still_valid = self._enabled and generation == self._generation
                    if not still_valid or self._closing.is_set():
                        continue
                    quick, response = harness.processar_mensagem(text)
                    answer = response if quick else getattr(response, "output_text", str(response))
                    answer = str(answer or "").strip() or "(Sem resposta textual.)"
                    # Desligar/reativar invalida resultados da geracao anterior.
                    with self._lock:
                        still_current = (
                            self._enabled
                            and generation == self._generation
                            and not self._closing.is_set()
                        )
                    if not still_current:
                        continue
                    snapshot = harness.current_task()
                    status = getattr(getattr(snapshot, "state", None), "value", "")
                    if status == "failed":
                        self.events.put(UiEvent("error", answer, generation=generation))
                    else:
                        self.events.put(UiEvent("reply", answer, generation=generation))
                except Exception as exc:
                    with self._lock:
                        still_current = (
                            self._enabled
                            and generation == self._generation
                            and not self._closing.is_set()
                        )
                    if still_current:
                        self.events.put(UiEvent("error", f"Erro ao processar: {exc}", generation=generation))
                finally:
                    self.events.put(UiEvent("idle", generation=generation))
        finally:
            self.deny_pending()
            self._dispose_harness()
            self.events.put(UiEvent("closed"))
