from __future__ import annotations

from queue import Queue
from threading import Event
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


# Tarefa 7: a janela de pre-roll deve ser limitada por amostras,
# independentemente do tamanho dos blocos entregues pelo PortAudio.
@pytest.mark.parametrize("block_samples", [480, 1600, 3200, 8000])
@pytest.mark.parametrize("as_list", [False, True])
def test_ptt_pre_roll_keeps_exact_latest_samples(block_samples, as_list):
    sample_rate = 16_000
    recorder = PushToTalkRecorder(
        sounddevice_module=object(), keyboard_module=object(),
    )
    recorder._preparar_buffer(sample_rate)
    limit = recorder._pre_roll_limit_samples
    all_audio = np.arange(block_samples * (limit // block_samples + 3), dtype=np.float32)
    for offset in range(0, len(all_audio), block_samples):
        original = all_audio[offset : offset + block_samples]
        block = original.tolist() if as_list else original.reshape(-1, 1)
        recorder._callback(block, len(block), None, None)

    saved = np.asarray(
        [sample for chunk in recorder._pre_roll
         for sample in np.asarray(chunk).reshape(-1)],
        dtype=np.float32,
    )
    assert recorder._pre_roll_samples == limit
    assert len(saved) == limit
    np.testing.assert_array_equal(saved, all_audio[-limit:])


def test_ptt_recording_starts_with_latest_pre_roll_before_new_frames():
    recorder = PushToTalkRecorder(
        sounddevice_module=object(), keyboard_module=object(),
    )
    recorder._preparar_buffer(16_000)
    before = np.arange(8_000, dtype=np.float32).reshape(-1, 1)
    recorder._callback(before, len(before), None, None)
    recorder._registrar_inicio()
    after = np.arange(8_000, 8_480, dtype=np.float32).reshape(-1, 1)
    recorder._callback(after, len(after), None, None)
    recorded = np.concatenate(recorder._registrar_fim(), axis=0).reshape(-1)

    np.testing.assert_array_equal(
        recorded, np.concatenate([before[-2_880:].reshape(-1), after.reshape(-1)])
    )
    assert recorder._pre_roll_samples == 0
    assert not recorder._pre_roll


def test_ptt_output_active_clears_and_blocks_pre_roll():
    recorder = PushToTalkRecorder(
        sounddevice_module=object(), keyboard_module=object(),
    )
    recorder._preparar_buffer(16_000)
    chunk = np.arange(3_200, dtype=np.float32).reshape(-1, 1)
    recorder._callback(chunk, len(chunk), None, None)
    assert recorder._pre_roll_samples == 2_880

    recorder.definir_saida_ativa(True)
    assert recorder._pre_roll_samples == 0
    assert not recorder._pre_roll
    recorder._callback(chunk, len(chunk), None, None)
    assert recorder._pre_roll_samples == 0
    assert not recorder._pre_roll

    recorder.definir_saida_ativa(False)
    recorder._callback(chunk, len(chunk), None, None)
    assert recorder._pre_roll_samples == 2_880
    recorder.limpar_pre_roll()
    assert recorder._pre_roll_samples == 0
    assert not recorder._pre_roll


# Testes exclusivos de compatibilidade e TTS migrados da suite V3.

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
    assert stt.repo_id == "calneymgp/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"

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


def test_asr_uses_explicit_local_path_and_required_int8_files():
    import inspect
    source = inspect.getsource(LocalPortugueseASR._ensure_model)
    download_source = inspect.getsource(LocalPortugueseASR._download_model)
    assert 'onnx_asr.load_model' in source
    assert 'path=str(model_dir)' in source
    assert 'encoder-model.int8.onnx' in download_source
    assert 'decoder_joint-model.int8.onnx' in download_source


def test_speech_formatter_for_youtube_confirms_completion():
    snapshot = SimpleNamespace(
        objective="Auren, abre o YouTube",
        result="Naveguei para: YouTube | URL atual: https://www.youtube.com/ | Modo do navegador: visivel",
        steps=(
            SimpleNamespace(
                tool="navegar_navegador",
                result="Naveguei para: YouTube | URL atual: https://www.youtube.com/ | Modo do navegador: visivel",
            ),
        ),
    )
    assert SpeechResponseFormatter.formatar(
        objetivo=snapshot.objective,
        texto=snapshot.result,
        snapshot=snapshot,
    ) == "YouTube aberto."


def test_tts_honors_cancel_event_without_chunking():
    event = Event()
    event.set()
    sd = _FakeSoundDevice()
    model = _FakeKokoro()
    tts = LocalKokoroTTS(model=model, sounddevice_module=sd)

    tts.falar("YouTube aberto.", cancel_event=event)

    assert model.calls == 1
    assert sd.streams == []


def test_tts_stable_stream_is_single_model_stream_call():
    sd = _FakeSoundDevice()
    model = _FakeKokoro()
    tts = LocalKokoroTTS(model=model, sounddevice_module=sd)

    tts.falar("YouTube aberto.")

    assert model.calls == 1
    assert len(sd.streams) == 1
    assert len(sd.streams[0].writes) == 2


def test_tts_reports_audio_start_callback_once():
    sd = _FakeSoundDevice()
    model = _FakeKokoro()
    tts = LocalKokoroTTS(model=model, sounddevice_module=sd)
    calls = []

    tts.falar("YouTube aberto.", on_audio_start=lambda: calls.append("started"))

    assert calls == ["started"]


class _FakeOutputStream:
    def __init__(self):
        self.writes = []

    def start(self):
        pass

    def write(self, audio):
        self.writes.append(audio)

    def stop(self):
        pass

    def close(self):
        pass


class _FakeSoundDevice:
    def __init__(self):
        self.streams = []

    def OutputStream(self, **kwargs):
        del kwargs
        stream = _FakeOutputStream()
        self.streams.append(stream)
        return stream


class _FakeKokoro: 
    def __init__(self):
        self.calls = 0

    async def create_stream(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        yield [0.1, 0.2], 22050
        yield [0.2, 0.3], 22050


def test_voice_main_does_not_use_spoken_cancel_keywords():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "voice" / "main.py").read_text(encoding="utf-8")
    assert "_eh_cancelamento" not in source
    assert "cancela isso" not in source
    assert "esquece" not in source


def test_tts_barge_in_aborts_long_chunk():
    import numpy as np
    cancel = Event()

    class Stream:
        def __init__(self):
            self.writes = []
            self.aborted = self.stopped = self.closed = 0
        def start(self): pass
        def write(self, audio):
            self.writes.append(len(audio))
            cancel.set()
        def abort(self): self.aborted += 1
        def stop(self): self.stopped += 1
        def close(self): self.closed += 1

    stream = Stream()
    class SD:
        def OutputStream(self, **kwargs): return stream
    class Model:
        def __init__(self): self.calls = 0
        async def create_stream(self, *args, **kwargs):
            self.calls += 1
            yield np.ones(64_000, dtype=np.float32), 16_000

    model = Model()
    LocalKokoroTTS(model=model, sounddevice_module=SD()).falar("teste", cancel_event=cancel)
    assert model.calls == 1
    assert stream.writes == [800]
    assert stream.aborted == 1 and stream.stopped == 0 and stream.closed == 1


def test_tts_barge_in_without_abort_uses_stop():
    import numpy as np
    cancel = Event()

    class Stream:
        def __init__(self): self.writes = []; self.stops = self.closed = 0
        def start(self): pass
        def write(self, audio):
            self.writes.append(len(audio))
            cancel.set()
        def stop(self): self.stops += 1
        def close(self): self.closed += 1

    stream = Stream()
    class SD:
        def OutputStream(self, **kwargs): return stream
    class Model:
        async def create_stream(self, *args, **kwargs):
            yield np.ones(32_000, dtype=np.float32), 16_000

    LocalKokoroTTS(model=Model(), sounddevice_module=SD()).falar("teste", cancel_event=cancel)
    assert stream.writes == [800] and stream.stops == 1 and stream.closed == 1


def test_tts_barge_in_keeps_audio_order_and_single_start():
    import numpy as np
    data = np.arange(2501, dtype=np.float32)

    class Stream:
        def __init__(self): self.parts = []; self.stops = self.closed = 0
        def start(self): pass
        def write(self, audio): self.parts.append(np.array(audio, copy=True))
        def stop(self): self.stops += 1
        def close(self): self.closed += 1

    stream = Stream()
    class SD:
        def OutputStream(self, **kwargs): return stream
    class Model:
        def __init__(self): self.calls = 0
        async def create_stream(self, *args, **kwargs):
            self.calls += 1
            yield data[:1200], 16_000
            yield data[1200:], 16_000

    model = Model()
    starts = []
    LocalKokoroTTS(model=model, sounddevice_module=SD()).falar(
        "teste", on_audio_start=lambda: starts.append("start")
    )
    assert model.calls == 1 and starts == ["start"]
    assert stream.stops == 1 and stream.closed == 1
    assert all(0 < len(part) <= 800 for part in stream.parts)
    np.testing.assert_array_equal(np.concatenate(stream.parts), data)


def test_tts_barge_in_releases_locks_after_write_error():
    import numpy as np
    import pytest
    from agent.ari_native.audio_manager import get_audio_output_lock

    class Stream:
        def __init__(self): self.writes = self.stops = self.closed = 0
        def start(self): pass
        def write(self, audio):
            self.writes += 1
            if self.writes == 2: raise OSError("falha simulada")
        def stop(self): self.stops += 1
        def close(self): self.closed += 1

    stream = Stream()
    class SD:
        def OutputStream(self, **kwargs): return stream
    class Model:
        async def create_stream(self, *args, **kwargs):
            yield np.ones(3200, dtype=np.float32), 16_000

    tts = LocalKokoroTTS(model=Model(), sounddevice_module=SD())
    with pytest.raises(RuntimeError, match="falha simulada"):
        tts.falar("teste")
    assert stream.writes == 2 and stream.stops == 1 and stream.closed == 1
    assert tts._lock.acquire(blocking=False)
    tts._lock.release()
    output_lock = get_audio_output_lock()
    assert output_lock.acquire(blocking=False)
    output_lock.release()
