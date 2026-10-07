from __future__ import annotations

from queue import Queue

import pytest

from core.confirmation import ConfirmationRequest, TextConfirmationChannel
from core.permission_manager import PermissionManager
from voice.confirmation import VoiceConfirmationChannel


def _request() -> ConfirmationRequest:
    return ConfirmationRequest(
        tool_name="encerrar_processo_windows",
        action="encerrar o processo '1234'",
        reason="Encerrar um processo pode perder trabalho.",
        actions_attempted=1,
        max_actions=10,
        actions_remaining=9,
    )


def test_text_confirmation_channel_preserves_interactive_behavior():
    prompts = []
    channel = TextConfirmationChannel(
        input_fn=lambda prompt: (prompts.append(prompt) or "s"),
    )

    assert channel.confirmar(_request()) is True
    assert prompts == ["Autorizar? [s/n]: "]


def test_permission_manager_delegates_confirmation_to_injected_channel(monkeypatch):
    captured = []

    class FakeChannel:
        def confirmar(self, request):
            captured.append(request)
            return True

    def fail_input(*_args, **_kwargs):
        raise AssertionError("PermissionManager nao deve ler stdin diretamente.")

    monkeypatch.setattr("builtins.input", fail_input)

    pm = PermissionManager(confirmation_channel=FakeChannel())
    permitido, motivo = pm.autorizar(
        "encerrar_processo_windows",
        {"pid": 4321, "nome": ""},
    )

    assert permitido is True
    assert motivo == "Usuario confirmou a acao."
    assert len(captured) == 1
    assert captured[0].tool_name == "encerrar_processo_windows"
    assert captured[0].actions_attempted == 1


def test_voice_confirmation_accepts_sim_from_shared_audio_queue():
    class FakeTTS:
        def __init__(self):
            self.falas = []

        def falar(self, texto):
            self.falas.append(texto)

    class FakeSTT:
        def transcrever(self, audio):
            assert audio == "audio-confirmacao"
            return "sim"

    audio_queue = Queue()
    audio_queue.put(("audio", "audio-confirmacao"))
    tts = FakeTTS()
    channel = VoiceConfirmationChannel(
        tts=tts,
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is True
    assert tts.falas and "Diga sim ou nao." in tts.falas[0]


def test_voice_confirmation_denies_on_timeout():
    class FakeTTS:
        def falar(self, _texto):
            pass

    class FakeSTT:
        def transcrever(self, _audio):
            raise AssertionError("ASR nao deveria ser chamado sem audio.")

    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=Queue(),
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is False


def test_voice_confirmation_rejects_legacy_raw_queue_item():
    class FakeTTS:
        def falar(self, _texto):
            pass

    class FakeSTT:
        def transcrever(self, _audio):
            raise AssertionError("Item fora do protocolo da fila nao pode chegar ao ASR.")

    audio_queue = Queue()
    audio_queue.put("audio-confirmacao")
    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is False


@pytest.mark.parametrize("resposta", ["sim", "Sim.", "sim!", "sim, pode"])
def test_voice_confirmation_accepts_common_affirmative_phrases(resposta):
    class FakeTTS:
        def falar(self, _texto):
            pass

    class FakeSTT:
        def transcrever(self, _audio):
            return resposta

    audio_queue = Queue()
    audio_queue.put(("audio", "audio-confirmacao"))
    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is True


def test_voice_confirmation_rejects_ambiguous_phrase():
    class FakeTTS:
        def falar(self, _texto):
            pass

    class FakeSTT:
        def transcrever(self, _audio):
            return "talvez, depois eu vejo"

    audio_queue = Queue()
    audio_queue.put(("audio", "audio-confirmacao"))
    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is False
