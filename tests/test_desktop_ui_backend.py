from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from types import SimpleNamespace

from core.confirmation import ConfirmationRequest
from ui.backend import AurenUiWorker, GuiConfirmationChannel, UiEvent


def _request() -> ConfirmationRequest:
    return ConfirmationRequest(
        tool_name="encerrar_processo_windows",
        action="Encerrar um processo",
        reason="Pode perder trabalho nao salvo",
        actions_attempted=1,
        max_actions=10,
        actions_remaining=9,
    )


def test_gui_confirmation_requires_explicit_approval():
    events: Queue[UiEvent] = Queue()
    active = []
    channel = GuiConfirmationChannel(events, active.append, timeout=2)
    result = []
    runner = Thread(target=lambda: result.append(channel.confirmar(_request())))
    runner.start()
    event = events.get(timeout=2)
    assert event.kind == "confirm"
    assert event.payload.action == "Encerrar um processo"
    event.payload.answer(True)
    runner.join(timeout=2)
    assert not runner.is_alive()
    assert result == [True]
    assert active[-1] is None


def test_gui_confirmation_times_out_closed_and_denies():
    events: Queue[UiEvent] = Queue()
    channel = GuiConfirmationChannel(events, lambda _choice: None, timeout=0.01)
    assert channel.confirmar(_request()) is False
    event = events.get_nowait()
    assert event.kind == "confirm"
    assert event.payload.approved is False
    assert event.payload.decided.is_set()


def test_gui_worker_lazy_harness_and_session_shutdown():
    created = []

    class FakeHarness:
        def __init__(self):
            self.commands = []
            self.closed = False
            self.session_closed = False

        def processar_mensagem(self, text):
            self.commands.append(text)
            return False, SimpleNamespace(output_text="Recebi: " + text)

        def current_task(self):
            return SimpleNamespace(state=SimpleNamespace(value="completed"))

        def cancel_current_task(self):
            return True

        def fechar(self):
            self.closed = True

        def _encerrar_sessao_chat(self, status):
            assert status == "closed"
            self.session_closed = True

    def factory(**kwargs):
        assert isinstance(kwargs["confirmation_channel"], GuiConfirmationChannel)
        instance = FakeHarness()
        created.append(instance)
        return instance

    worker = AurenUiWorker(harness_factory=factory)
    assert created == []
    worker.start()
    try:
        assert worker.submit("ola") is False  # comeca desligado
        worker.activate()
        assert worker.submit("ola")
        received = []
        while "idle" not in received:
            event = worker.events.get(timeout=3)
            received.append(event.kind)
            if event.kind == "reply":
                assert event.text == "Recebi: ola"
        assert len(created) == 1
        assert created[0].commands == ["ola"]

        worker.go_off()
        while True:
            event = worker.events.get(timeout=3)
            if event.kind == "off":
                break
        assert created[0].closed
        assert created[0].session_closed
        assert worker.submit("com o Auren desligado") is False

        worker.activate()
        assert worker.submit("segunda conversa")
        while True:
            event = worker.events.get(timeout=3)
            if event.kind == "reply":
                assert event.text == "Recebi: segunda conversa"
            if event.kind == "idle":
                break
        assert len(created) == 2
    finally:
        worker.close()
        worker._thread.join(timeout=3)
    assert not worker.alive
    assert created[-1].session_closed
    assert worker.submit("depois do fechamento") is False


def test_gui_worker_does_not_duplicate_dispatcher():
    # A ponte tem somente a API do Harness; nao chama handlers nem
    # implementa uma segunda rota de execucao do modelo.
    from pathlib import Path
    source = (Path(__file__).parents[1] / "ui" / "backend.py").read_text(encoding="utf-8")
    assert "harness.processar_mensagem(text)" in source
    assert "auren.criar_harness(confirmation_channel=channel)" in source
    assert "executar_ferramenta(" not in source

def test_desktop_frontend_has_valid_python_syntax():
    from pathlib import Path
    ui_file = Path(__file__).parents[1] / "interface_auren.py"
    compile(ui_file.read_text(encoding="utf-8"), str(ui_file), "exec")


def test_timeout_confirmation_enqueues_close_dialog_event():
    events: Queue[UiEvent] = Queue()
    channel = GuiConfirmationChannel(events, lambda _choice: None, timeout=0.01)
    assert channel.confirmar(_request()) is False
    assert events.get_nowait().kind == "confirm"
    assert events.get_nowait().kind == "notice"
    assert events.get_nowait().kind == "confirm_done"


def test_worker_suppresses_reply_from_previous_session_after_off():
    started, release = Event(), Event()

    class SlowHarness:
        def processar_mensagem(self, text):
            started.set()
            release.wait(timeout=3)
            return False, SimpleNamespace(output_text="resposta antiga")

        def current_task(self):
            return SimpleNamespace(state=SimpleNamespace(value="completed"))

        def cancel_current_task(self):
            pass

        def fechar(self):
            pass

        def _encerrar_sessao_chat(self, status):
            pass

    worker = AurenUiWorker(harness_factory=lambda **_: SlowHarness())
    worker.start()
    try:
        worker.activate()
        assert worker.submit("ola")
        assert started.wait(timeout=2)
        worker.go_off()
        release.set()
        received = []
        while "off" not in received:
            received.append(worker.events.get(timeout=3).kind)
        assert "reply" not in received
    finally:
        release.set()
        worker.close()
        worker._thread.join(timeout=3)
