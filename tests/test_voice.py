from __future__ import annotations

from queue import Queue
from types import SimpleNamespace

import numpy as np

from voice.confirmation import VoiceConfirmationChannel
from voice.input import AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from voice.segmentation import VoiceActivitySegmenter, VoiceSegmentConfig
from voice.speech_response import SpeechResponseFormatter
from voice.stt import LocalPortugueseASR
from voice.tts import LocalKokoroTTS


def test_voice_v4_components_are_lazy_and_constructible():
    recorder = PushToTalkRecorder(
        hotkey="right ctrl",
        config=AudioCaptureConfig(min_seconds=0.1),
        sounddevice_module=object(),
        keyboard_module=object(),
    )
    assert recorder.hotkey == "right ctrl"
    assert recorder.config.sample_rate == 16_000
    assert recorder.config.pre_roll_seconds == 0.18
    assert recorder.config.post_roll_seconds == 0.12
    assert recorder.config.key_debounce_seconds == 0.06

    stt = LocalPortugueseASR(model=object())
    assert stt.language == "pt"
    assert stt.target_sample_rate == 16_000
    assert "TAGARELA" in stt.repo_id

    tts = LocalKokoroTTS(model=object(), sounddevice_module=object())
    assert tts.voice == "pm_alex"
    assert tts.lang == "pt-br"


def test_captured_audio_keeps_capture_sample_rate():
    captured = CapturedAudio(
        samples=[0.0, 0.1],
        sample_rate=48000,
        duration=0.1,
        rms=0.05,
        peak=0.1,
        device_name="Microfone Realtek",
        speech_detected=True,
        vad_backend="webrtcvad",
    )
    assert captured.sample_rate == 48000
    assert captured.device_name.startswith("Microfone")
    assert captured.speech_detected is True
    assert captured.vad_backend == "webrtcvad"


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


def test_asr_resamples_capture_audio_to_16khz():
    class FakeModel:
        def __init__(self):
            self.calls = []

        def recognize(self, waveform, sample_rate=None, language=None, channel=None):
            self.calls.append((waveform, sample_rate, language, channel))
            return "Auren, teste local."

    model = FakeModel()
    asr = LocalPortugueseASR(model=model)
    captured = CapturedAudio(
        samples=np.full(4800, 0.1, dtype=np.float32),
        sample_rate=48000,
        duration=0.1,
        rms=0.1,
        peak=0.1,
        device_name="Realtek",
    )
    assert asr.transcrever(captured) == "Auren, teste local."
    waveform, sample_rate, language, channel = model.calls[0]
    assert sample_rate == 16_000
    assert language == "pt"
    assert channel == "mean"
    assert len(waveform) == 1600
    assert waveform.dtype == np.float32


def test_asr_returns_empty_for_too_short_audio_without_inference():
    class FakeModel:
        def recognize(self, *args, **kwargs):
            raise AssertionError("audio curto nao deveria chegar ao modelo")

    asr = LocalPortugueseASR(model=FakeModel())
    assert asr.transcrever(
        CapturedAudio(
            samples=np.zeros(100, dtype=np.float32),
            sample_rate=16_000,
            duration=0.006,
            rms=0.0,
            peak=0.0,
            device_name="Realtek",
        )
    ) == ""


def test_voice_segmenter_keeps_start_and_end_padding():
    class FakeVad:
        def __init__(self):
            self.calls = 0

        def is_speech(self, frame, sample_rate):
            assert sample_rate == 16_000
            self.calls += 1
            return 10 <= self.calls <= 19

    config = VoiceSegmentConfig(
        frame_duration_ms=20,
        start_padding_ms=80,
        end_padding_ms=120,
        min_speech_seconds=0.08,
        silence_rms=0.0008,
        silence_peak=0.005,
    )
    segmenter = VoiceActivitySegmenter(config=config, vad=FakeVad())
    audio = np.zeros(16_000, dtype=np.float32)
    audio[3200:6400] = 0.15

    result = segmenter.segment(audio, 16_000)

    assert result is not None
    assert result.speech_detected is True
    assert result.vad_backend == "webrtcvad"
    assert result.sample_rate == 16_000
    assert 0.38 <= result.duration <= 0.42


def test_voice_segmenter_rejects_near_silence():
    segmenter = VoiceActivitySegmenter()
    audio = np.full(16_000, 0.00001, dtype=np.float32)
    assert segmenter.segment(audio, 16_000) is None


def test_named_microphone_is_resolved_against_current_devices():
    class FakeSoundDevice:
        def query_devices(self, *args, **kwargs):
            if args or kwargs:
                return {"name": "USB Microphone", "default_samplerate": 48000}
            return [
                {"name": "Notebook Mic", "max_input_channels": 2},
                {"name": "USB Microphone", "max_input_channels": 1},
            ]

    recorder = PushToTalkRecorder(
        sounddevice_module=FakeSoundDevice(),
        keyboard_module=object(),
    )
    recorder._device_index = "USB Microphone"

    assert recorder._resolver_dispositivo() == 1


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


def test_voice_confirmation_unpacks_capture_queue_envelope():
    class FakeTTS:
        def __init__(self):
            self.spoken = []

        def falar(self, text):
            self.spoken.append(text)

    class FakeSTT:
        def transcrever(self, audio):
            assert isinstance(audio, CapturedAudio)
            return "sim"

    queue = Queue()
    queue.put(
        (
            "audio",
            CapturedAudio(
                samples=np.zeros(1600, dtype=np.float32),
                sample_rate=16_000,
                duration=0.1,
                rms=0.1,
                peak=0.1,
                device_name="Realtek",
            ),
        )
    )
    tts = FakeTTS()
    channel = VoiceConfirmationChannel(
        tts=tts,
        stt=FakeSTT(),
        audio_queue=queue,
        timeout=0.1,
    )

    request = SimpleNamespace(action="definir volume", reason="e necessario confirmar")
    assert channel.confirmar(request) is True
    assert tts.spoken
