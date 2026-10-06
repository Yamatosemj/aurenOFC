from __future__ import annotations

from types import SimpleNamespace

from voice.input import AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from voice.speech_response import SpeechResponseFormatter
from voice.stt import LocalPortugueseASR
from voice.tts import LocalKokoroTTS


def test_voice_v3_components_are_lazy_and_constructible():
    recorder = PushToTalkRecorder(
        hotkey="f8",
        config=AudioCaptureConfig(min_seconds=0.1),
        sounddevice_module=object(),
        keyboard_module=object(),
    )
    assert recorder.hotkey == "f8"

    stt = LocalPortugueseASR(model=object())
    assert stt.language == "pt"
    assert "TAGARELA" in stt.repo_id

    tts = LocalKokoroTTS(model=object(), sounddevice_module=object())
    assert tts.voice == "pm_alex"
    assert tts.lang == "pt-br"


def test_captured_audio_keeps_native_sample_rate():
    captured = CapturedAudio(
        samples=[0.0, 0.1],
        sample_rate=48000,
        duration=0.1,
        rms=0.05,
        peak=0.1,
        device_name="Microfone Realtek",
    )
    assert captured.sample_rate == 48000
    assert captured.device_name.startswith("Microfone")


def test_speech_formatter_for_clock_is_short_and_objective():
    snapshot = SimpleNamespace(
        objective="Auren, que horas são?",
        result="Hora local: 17:51:12\nData local: 21/09/2026\nRAM: 11.6 GB de 23.7 GB (48% usada)",
        steps=(
            SimpleNamespace(
                tool="obter_status_windows",
                result="Hora local: 17:51:12\nData local: 21/09/2026\nRAM: 11.6 GB de 23.7 GB (48% usada)",
            ),
        ),
    )
    assert SpeechResponseFormatter.formatar(
        objetivo=snapshot.objective,
        texto=snapshot.result,
        snapshot=snapshot,
    ) == "Agora são 17:51."


def test_speech_formatter_for_volume_does_not_read_raw_tool_dump():
    snapshot = SimpleNamespace(
        objective="Auren, coloque o volume em 50 por cento",
        result="Volume definido para 50%.",
        steps=(SimpleNamespace(tool="definir_volume_windows", result="Volume definido para 50%."),),
    )
    assert SpeechResponseFormatter.formatar(
        objetivo=snapshot.objective,
        texto=snapshot.result,
        snapshot=snapshot,
    ) == "Volume ajustado para 50%."


def test_fallback_keeps_general_model_answer_short():
    answer = "Primeira frase objetiva. Segunda frase também objetiva. Terceira frase não deveria ser lida."
    assert SpeechResponseFormatter.formatar(objetivo="fale comigo", texto=answer) == (
        "Primeira frase objetiva. Segunda frase também objetiva."
    )


def test_asr_forwards_native_sample_rate_to_local_model():
    class FakeModel:
        def __init__(self):
            self.calls = []

        def recognize(self, waveform, sample_rate=None, language=None, channel=None):
            self.calls.append((waveform, sample_rate, language, channel))
            return "Auren, teste local."

    model = FakeModel()
    asr = LocalPortugueseASR(model=model)
    captured = CapturedAudio(
        samples=[0.1, 0.2],
        sample_rate=48000,
        duration=0.01,
        rms=0.1,
        peak=0.2,
        device_name="Realtek",
    )
    assert asr.transcrever(captured) == "Auren, teste local."
    assert model.calls[0][1:] == (48000, "pt", "mean")


def test_kokoro_tts_streams_audio_without_sapi():
    class FakeStream:
        def __init__(self):
            self.started = False
            self.writes = 0
            self.stopped = False
            self.closed = False

        def start(self):
            self.started = True

        def write(self, audio):
            assert len(audio) > 0
            self.writes += 1

        def stop(self):
            self.stopped = True

        def close(self):
            self.closed = True

    class FakeSoundDevice:
        def __init__(self):
            self.stream = None

        def OutputStream(self, **kwargs):
            self.stream = FakeStream()
            return self.stream

    class FakeKokoro:
        async def create_stream(self, text, voice, speed, lang):
            assert text == "Olá Auren."
            assert voice == "pm_alex"
            assert lang == "pt-br"
            yield [0.0, 0.1, -0.1], 24000

    sd = FakeSoundDevice()
    tts = LocalKokoroTTS(model=FakeKokoro(), sounddevice_module=sd)
    tts.falar("Olá Auren.")
    assert sd.stream is not None
    assert sd.stream.started is True
    assert sd.stream.writes == 1
    assert sd.stream.stopped is True
    assert sd.stream.closed is True
