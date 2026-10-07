from __future__ import annotations

from queue import Queue
from threading import Thread
import time

import pytest

from core.confirmation import ConfirmationRequest, TextConfirmationChannel
from core.permission_manager import PermissionManager
from voice.confirmation import VoiceConfirmationChannel
from voice.input import CapturedAudio


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
            assert isinstance(audio, CapturedAudio)
            return "sim"

    audio_queue = Queue()
    audio_queue.put(("audio", _captured_audio(time.perf_counter())))
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
    audio_queue.put(("audio", _captured_audio(time.perf_counter())))
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



def _captured_audio(captured_at: float) -> CapturedAudio:
    return CapturedAudio(
        samples=[0.1, 0.2],
        sample_rate=16000,
        duration=0.01,
        rms=0.1,
        peak=0.2,
        device_name="microfone-test",
        captured_at=captured_at,
    )


def test_voice_confirmation_discards_stale_audio_and_accepts_fresh_capture():
    audio_queue = Queue()
    transcribed = []

    class FakeTTS:
        def falar(self, _texto):
            audio_queue.put(("audio", _captured_audio(time.perf_counter())))

            def put_fresh_audio():
                time.sleep(0.01)
                audio_queue.put(("audio", _captured_audio(time.perf_counter())))

            Thread(target=put_fresh_audio, daemon=True).start()

    class FakeSTT:
        def transcrever(self, audio):
            transcribed.append(audio)
            return "sim"

    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.2,
    )

    assert channel.confirmar(_request()) is True
    assert len(transcribed) == 1
    assert transcribed[0].captured_at > 0

def test_voice_confirmation_stops_on_real_capture_error_without_calling_asr():
    class FakeTTS:
        def falar(self, _texto):
            pass

    class FakeSTT:
        def transcrever(self, _audio):
            raise AssertionError("Erro de captura nao pode chegar ao ASR.")

    audio_queue = Queue()
    audio_queue.put(("erro", RuntimeError("microfone indisponivel")))
    channel = VoiceConfirmationChannel(
        tts=FakeTTS(),
        stt=FakeSTT(),
        audio_queue=audio_queue,
        timeout=0.1,
    )

    assert channel.confirmar(_request()) is False
