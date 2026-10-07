from __future__ import annotations

import asyncio
from threading import Event
from types import SimpleNamespace

from voice.input import AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from voice.speech_response import SpeechResponseFormatter
from voice.stt import ASR_EXPECTED, ASR_REVISION, LocalPortugueseASR
from voice.tts import MODEL_PATH, TTS_EXPECTED, VOICES_PATH, LocalKokoroTTS


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


def test_voice_main_does_not_use_spoken_cancel_keywords():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "voice" / "main.py").read_text(encoding="utf-8")
    assert "_eh_cancelamento" not in source
    assert "cancela isso" not in source
    assert "esquece" not in source


def test_tts_is_safe_when_called_from_an_existing_event_loop():
    import asyncio
    from threading import Thread

    sd = _FakeSoundDevice()
    model = _FakeKokoro()
    tts = LocalKokoroTTS(model=model, sounddevice_module=sd)
    erro = []

    def trabalhador():
        async def executar():
            tts.falar("YouTube aberto.")

        try:
            asyncio.run(executar())
        except BaseException as exc:
            erro.append(exc)

    thread = Thread(target=trabalhador, daemon=True)
    thread.start()
    thread.join()

    assert erro == []
    assert model.calls == 1
    assert len(sd.streams) == 1


def test_voice_model_manifests_pin_immutable_sources_and_known_artifacts():
    assert ASR_REVISION == "f5f837ee9e385781e60748cb9824a9c65487be36"
    assert set(ASR_EXPECTED) == {
        "encoder-model.int8.onnx",
        "decoder_joint-model.int8.onnx",
        "nemo128.onnx",
    }
    assert set(TTS_EXPECTED) == {
        MODEL_PATH.name,
        VOICES_PATH.name,
    }


def test_tts_rejects_wrong_checksum_without_loading_model(tmp_path):
    import voice.tts as tts_module

    model_path = tmp_path / MODEL_PATH.name
    model_path.write_bytes(b"corrompido")

    try:
        tts_module.LocalKokoroTTS._verify_file(model_path)
    except RuntimeError as exc:
        assert "SHA-256 invalido" in str(exc) or "tamanho inesperado" in str(exc)
    else:
        raise AssertionError("artefato corrompido deveria ser rejeitado")

    assert not model_path.exists()


def test_asr_verifier_rejects_corrupted_binary(tmp_path):
    import voice.stt as stt_module

    model_dir = tmp_path / "asr"
    model_dir.mkdir()
    for name in ("config.json", "decoder_joint-model.int8.onnx", "encoder-model.int8.onnx", "nemo128.onnx", "vocab.txt"):
        (model_dir / name).write_bytes(b"conteudo-invalido")

    invalid = stt_module.LocalPortugueseASR._verify_model_files(model_dir)

    assert ("sha256:encoder-model.int8.onnx" in invalid or "tamanho:encoder-model.int8.onnx" in invalid)
    assert ("sha256:decoder_joint-model.int8.onnx" in invalid or "tamanho:decoder_joint-model.int8.onnx" in invalid)
    assert ("sha256:nemo128.onnx" in invalid or "tamanho:nemo128.onnx" in invalid)


def test_asr_verifier_requires_all_model_files(tmp_path):
    import voice.stt as stt_module

    model_dir = tmp_path / "asr"
    model_dir.mkdir()

    invalid = stt_module.LocalPortugueseASR._verify_model_files(model_dir)

    assert "ausente:config.json" in invalid
    assert "ausente:vocab.txt" in invalid
    assert "ausente:encoder-model.int8.onnx" in invalid
