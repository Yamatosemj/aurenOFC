from __future__ import annotations

from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest

from voice.confirmation import VoiceConfirmationChannel
from voice.input import AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from voice.segmentation import VoiceActivitySegmenter, VoiceSegmentConfig
from voice.speech_response import SpeechResponseFormatter
from voice.stt import LocalPortugueseASR
from voice.tts import LocalKokoroTTS


def test_voice_v4_components_are_lazy_and_constructible():
    recorder = PushToTalkRecorder(
        hotkey="right ctrl+right shift",
        config=AudioCaptureConfig(min_seconds=0.1),
        sounddevice_module=object(),
        keyboard_module=object(),
    )
    assert recorder.hotkey == "right ctrl+right shift"
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


def test_asr_boosts_low_level_segment_without_clipping():
    class FakeModel:
        def __init__(self):
            self.waveform = None

        def recognize(self, waveform, sample_rate=None, language=None, channel=None):
            self.waveform = waveform
            return "teste"

    model = FakeModel()
    asr = LocalPortugueseASR(model=model)
    captured = CapturedAudio(
        samples=np.full(1600, 0.006, dtype=np.float32),
        sample_rate=16_000,
        duration=0.1,
        rms=0.006,
        peak=0.006,
        device_name="Realtek",
    )

    assert asr.transcrever(captured) == "teste"
    assert model.waveform is not None
    assert float(np.sqrt(np.mean(np.square(model.waveform)))) > 0.02
    assert float(np.max(np.abs(model.waveform))) <= 0.95


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


def test_voice_segmenter_prepares_low_level_audio_for_vad_without_clipping():
    audio = np.full(1600, 0.006, dtype=np.float32)
    prepared = VoiceActivitySegmenter._preparar_nivel_para_vad(audio)
    assert float(np.sqrt(np.mean(np.square(prepared)))) > 0.01
    assert float(np.max(np.abs(prepared))) <= 0.95


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


class _FakeInputStream:
    def __init__(self, callback=None):
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class _FakeInputSoundDevice:
    def __init__(self, *, native_rate=48_000, accepted_rates=(48_000,)):
        self.native_rate = int(native_rate)
        self.accepted_rates = set(accepted_rates)
        self.attempted_rates = []
        self.attempted_devices = []
        self.streams = []

    def query_devices(self, *args, **kwargs):
        default_info = {
            "name": "Default Mic",
            "max_input_channels": 1,
            "default_samplerate": float(self.native_rate),
        }
        if not args and not kwargs:
            return [default_info]

        device = args[0] if args else kwargs.get("device")
        kind = args[1] if len(args) > 1 else kwargs.get("kind")
        if device is None and kind == "input":
            return default_info
        if isinstance(device, int) and device == 0:
            return default_info
        raise RuntimeError(f"dispositivo nao encontrado: {device}")

    def InputStream(self, **kwargs):
        rate = int(kwargs["samplerate"])
        self.attempted_rates.append(rate)
        self.attempted_devices.append(kwargs.get("device"))
        if rate not in self.accepted_rates:
            raise RuntimeError(f"taxa {rate} Hz rejeitada pelo dispositivo")
        stream = _FakeInputStream(callback=kwargs.get("callback"))
        self.streams.append(stream)
        return stream


class _EscapeKeyboard:
    def is_pressed(self, key):
        return key == "esc"


class _CaptureKeyboard:
    def __init__(self, sounddevice):
        self.sounddevice = sounddevice
        self.fed_audio = False
        self.hotkey_checks = 0

    def is_pressed(self, key):
        if key == "esc":
            if not self.fed_audio:
                stream = self.sounddevice.streams[-1]
                samples = np.full(6_000, 0.1, dtype=np.float32)
                stream.callback(samples, len(samples), None, None)
                self.fed_audio = True
            return False
        if key == "right ctrl+right shift":
            self.hotkey_checks += 1
            return self.hotkey_checks <= 2
        return False


class _PassThroughSegmenter:
    def segment(self, audio, sample_rate):
        return SimpleNamespace(
            samples=audio,
            sample_rate=sample_rate,
            speech_detected=True,
            vad_backend="fake",
        )


def test_input_stream_uses_native_rate_when_preferred_rate_is_rejected():
    sd = _FakeInputSoundDevice(native_rate=48_000, accepted_rates=(48_000,))
    recorder = PushToTalkRecorder(
        config=AudioCaptureConfig(sample_rate=16_000),
        sounddevice_module=sd,
        keyboard_module=object(),
    )

    device_name, native_rate = recorder._input_device_info(0)
    stream, actual_rate = recorder._abrir_stream(
        device=0,
        device_name=device_name,
        preferred_rate=16_000,
        native_rate=native_rate,
    )

    assert native_rate == 48_000
    assert actual_rate == 48_000
    assert sd.attempted_rates == [16_000, 48_000]
    assert stream.started is True


def test_input_stream_stops_after_preferred_rate_succeeds():
    sd = _FakeInputSoundDevice(native_rate=48_000, accepted_rates=(16_000, 48_000))
    recorder = PushToTalkRecorder(
        config=AudioCaptureConfig(sample_rate=16_000),
        sounddevice_module=sd,
        keyboard_module=object(),
    )
    device_name, native_rate = recorder._input_device_info(0)

    stream, actual_rate = recorder._abrir_stream(
        device=0,
        device_name=device_name,
        preferred_rate=16_000,
        native_rate=native_rate,
    )

    assert actual_rate == 16_000
    assert sd.attempted_rates == [16_000]
    assert stream.started is True


def test_missing_named_microphone_uses_default_and_preserves_opened_rate(monkeypatch):
    monkeypatch.setenv("AUREN_MIC_DEVICE", "Microfone que nao existe")
    sd = _FakeInputSoundDevice(native_rate=48_000, accepted_rates=(44_100,))
    recorder = PushToTalkRecorder(
        config=AudioCaptureConfig(
            sample_rate=16_000,
            min_seconds=0.1,
            post_roll_seconds=0.0,
            key_debounce_seconds=0.0,
        ),
        sounddevice_module=sd,
        keyboard_module=_CaptureKeyboard(sd),
        segmenter=_PassThroughSegmenter(),
    )

    captured = recorder._capturar_com_lock()

    assert captured is not None
    assert captured.sample_rate == 44_100
    assert sd.attempted_rates == [16_000, 48_000, 44_100]
    assert sd.attempted_devices == [None, None, None]
    assert recorder._last_device_name == "Default Mic"
    assert recorder._last_sample_rate == captured.sample_rate
    assert sd.streams[0].started is True
    assert sd.streams[0].stopped is True
    assert sd.streams[0].closed is True


def test_input_stream_error_lists_all_unique_rates_attempted():
    sd = _FakeInputSoundDevice(native_rate=48_000, accepted_rates=())
    recorder = PushToTalkRecorder(
        config=AudioCaptureConfig(sample_rate=16_000),
        sounddevice_module=sd,
        keyboard_module=object(),
    )
    device_name, native_rate = recorder._input_device_info(0)

    with pytest.raises(RuntimeError) as exc_info:
        recorder._abrir_stream(
            device=0,
            device_name=device_name,
            preferred_rate=16_000,
            native_rate=native_rate,
        )

    assert sd.attempted_rates == [16_000, 48_000, 44_100]
    error = str(exc_info.value)
    assert "16000 Hz" in error
    assert "48000 Hz" in error
    assert "44100 Hz" in error


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
