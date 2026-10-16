"""Corridas entre Desligar, reativar e eventos atrasados da UI.

Nenhum servidor externo, Electron real, GUI, API ou ferramentas mutáveis.
Os cenarios temporizados usam Event, nao sleeps arbitrarios.
"""
from __future__ import annotations

from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace

from core.confirmation import ConfirmationRequest
from ui.backend import AurenUiWorker, ConfirmationChoice, UiEvent
from ui.chrome_server import LocalChromeApp


class ControlledHarness:
    def __init__(self, channel, start_old, release_old, start_new, release_new):
        self.channel = channel
        self.start_old = start_old
        self.release_old = release_old
        self.start_new = start_new
        self.release_new = release_new

    def processar_mensagem(self, text):
        if text == "antiga":
            self.start_old.set()
            if not self.release_old.wait(3):
                raise AssertionError("Timeout do teste antigo")
            return False, SimpleNamespace(output_text="resposta obsoleta")
        if text == "nova":
            self.start_new.set()
            if not self.release_new.wait(3):
                raise AssertionError("Timeout do teste novo")
            return False, SimpleNamespace(output_text="resposta atual")
        raise AssertionError(text)

    def current_task(self):
        return SimpleNamespace(state=SimpleNamespace(value="completed"))

    def cancel_current_task(self):
        pass

    def fechar(self):
        pass

    def _encerrar_sessao_chat(self, status):
        assert status == "closed"


def test_off_then_reactivate_drops_stale_idle_and_off_before_new_reply():
    old_started, old_release = Event(), Event()
    new_started, new_release = Event(), Event()
    created = []

    def factory(confirmation_channel):
        h = ControlledHarness(
            confirmation_channel, old_started, old_release, new_started, new_release
        )
        created.append(h)
        return h

    worker = AurenUiWorker(harness_factory=factory)
    app = LocalChromeApp(worker)
    try:
        app.submit("antiga")
        assert old_started.wait(2)
        assert app.change_mode("off") == {"mode": "off"}
        assert app.submit("nova") == {"accepted": True, "mode": "active"}
        old_release.set()
        assert new_started.wait(2), "A nova sessao deve iniciar apos descarte da antiga"

        snapshot = app.snapshot()
        assert snapshot["mode"] == "active"
        assert snapshot["busy"] is True, "idle atrasado nao pode liberar outra submissao"
        kinds = [event["kind"] for event in snapshot["events"]]
        assert "off" not in kinds, "off da sessao anterior nao pode desligar a nova"
        assert not any(
            e["kind"] in {"reply", "error"} and e["text"] == "resposta obsoleta"
            for e in snapshot["events"]
        )
        assert len(created) == 2
        new_release.set()
        worker._thread.join(timeout=0.01)  # nao bloqueia espera de nova resposta
        result = app.snapshot()
        # A fila da nova resposta pode ainda estar em transito.
        assert result["mode"] == "active"
    finally:
        old_release.set()
        new_release.set()
        app.shutdown()
        worker._thread.join(timeout=3)
        assert not worker.alive


def test_old_confirm_event_is_denied_and_never_exposed_to_chrome():
    class FakeWorker:
        def __init__(self):
            self.events = Queue()
            self.generation = 12
        def start(self):
            pass

    worker = FakeWorker()
    app = LocalChromeApp(worker)
    app.mode = "active"
    app.busy = True
    choice = ConfirmationChoice("Apagar?", "Teste", "encerrar_processo_windows")
    worker.events.put(UiEvent("idle", generation=11))
    worker.events.put(UiEvent("off", generation=11))
    worker.events.put(UiEvent("reply", "antiga", generation=11))
    worker.events.put(UiEvent("confirm", payload=choice, generation=11))
    snapshot = app.snapshot()
    assert snapshot["mode"] == "active"
    assert snapshot["busy"] is True
    assert snapshot["events"] == []
    assert app.pending is None
    assert choice.decided.is_set()
    assert choice.approved is False


def test_confirmation_after_session_invalidated_denies_immediately():
    called, resume = Event(), Event()
    confirmations = []

    class LateConfirmationHarness:
        def __init__(self, channel):
            self.channel = channel
        def processar_mensagem(self, text):
            called.set()
            assert resume.wait(3)
            request = ConfirmationRequest(
                tool_name="encerrar_processo_windows",
                action="Fechar processo",
                reason="Teste isolado",
                actions_attempted=1,
                max_actions=10,
                actions_remaining=9,
            )
            confirmations.append(self.channel.confirmar(request))
            return False, SimpleNamespace(output_text="cancelado")
        def cancel_current_task(self):
            pass
        def fechar(self):
            pass
        def _encerrar_sessao_chat(self, status):
            pass

    worker = AurenUiWorker(harness_factory=lambda confirmation_channel: LateConfirmationHarness(confirmation_channel))
    worker.start()
    try:
        worker.activate()
        assert worker.submit("antiga")
        assert called.wait(2)
        worker.go_off()
        resume.set()
        seen = []
        while "off" not in seen:
            event = worker.events.get(timeout=3)
            seen.append(event.kind)
        assert confirmations == [False], "Nenhum modal tardio pode ficar esperando timeout"
        assert "confirm" not in seen
    finally:
        resume.set()
        worker.close()
        worker._thread.join(timeout=3)


def test_confirm_choice_is_idempotent_when_cancelled():
    choice = ConfirmationChoice("Acao", "Motivo", "tool")
    choice.answer(False)
    thread = Thread(target=lambda: choice.answer(True))
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert choice.decided.is_set() and choice.approved is False


def test_tk_frontend_filters_session_generation_without_changing_layout():
    from pathlib import Path
    frontend = Path(__file__).resolve().parents[1] / "interface_auren.py"
    source = frontend.read_text(encoding="utf-8")
    compile(source, str(frontend), "exec")
    assert "event.generation is not None" in source
    assert "event.generation != self.worker.generation" in source
