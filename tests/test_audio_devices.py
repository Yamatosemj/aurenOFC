from __future__ import annotations

import logging
import time

import pytest

import voice.audio_devices as audio


class _Stream:
    def __init__(self, *, callback=None, write_delay=0.0, input_frames=None):
        self.callback = callback
        self.write_delay = write_delay
        self.input_frames = input_frames
        self.device = None
        self.started = False
        self.closed = False

    def start(self):
        self.started = True
        if self.callback is not None and self.input_frames is not None:
            self.callback(None, self.input_frames)

    def write(self, data):
        if self.write_delay:
            time.sleep(self.write_delay)

    def stop(self):
        pass

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self, devices, apis, *, slow_output=True):
        self.devices = devices
        self.apis = apis
        self.slow_output = slow_output
        self.output_stream_devices = []

    def query_devices(self, *args, **kwargs):
        if args and isinstance(args[0], int):
            return self.devices[args[0]]
        if kwargs.get("kind") == "input":
            return next(d for d in self.devices if d.get("max_input_channels", 0))
        if kwargs.get("kind") == "output":
            return next(d for d in self.devices if d.get("max_output_channels", 0))
        return list(self.devices)

    def query_hostapis(self):
        return [{"name": name} for name in self.apis]

    def InputStream(self, **kwargs):
        stream = _Stream(
            callback=kwargs.get("callback"),
            input_frames=int(
                audio._RATES["input"] * audio._PROBE_SECONDS["input"] * 0.8
            ),
        )
        stream.device = kwargs.get("device")
        return stream

    def OutputStream(self, **kwargs):
        delay = audio._PROBE_SECONDS["output"] if self.slow_output else 0.0
        stream = _Stream(write_delay=delay)
        stream.device = kwargs.get("device")
        self.output_stream_devices.append(stream.device)
        return stream


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    audio._cache = None
    audio._probe_results.clear()
    audio._chosen_api["input"] = None
    audio._chosen_api["output"] = None
    monkeypatch.setattr(
        audio,
        "_config_path",
        lambda: tmp_path / "Auren" / "audio_devices.json",
    )
    monkeypatch.setattr(audio.platform, "system", lambda: "Windows")
    monkeypatch.delenv("AUREN_AUDIO_PROBE", raising=False)


def _devices():
    apis = ["MME", "Windows DirectSound", "Windows WASAPI", "WDM-KS"]
    devices = []
    for api_i in range(4):
        for i in range(1, 5):
            devices.append(
                {
                    "name": f"Mic {i}",
                    "max_input_channels": 1,
                    "max_output_channels": 0,
                    "hostapi": api_i,
                }
            )
        for i in range(1, 5):
            devices.append(
                {
                    "name": f"Headset {i}",
                    "max_input_channels": 0,
                    "max_output_channels": 2,
                    "hostapi": api_i,
                }
            )
    for name in (
        "Microsoft Sound Mapper - Input",
        "Primary Sound Capture Driver",
        "Microsoft Sound Mapper - Output",
        "Primary Sound Driver",
        "Surround 5.1",
        "",
        "Named zero",
        "Null Output",
        "Sysdefault",
    ):
        devices.append(
            {
                "name": name,
                "max_input_channels": 0,
                "max_output_channels": 0,
                "hostapi": 0,
            }
        )
    assert len(devices) == 41
    return devices, apis


def test_41_raw_entries_become_4_unique_names_per_direction(monkeypatch):
    devices, apis = _devices()
    monkeypatch.setattr(
        audio,
        "_obter_sounddevice",
        lambda: FakeSoundDevice(devices, apis),
    )

    assert audio.listar_dispositivos("input") == ["Mic 1", "Mic 2", "Mic 3", "Mic 4"]
    assert audio.listar_dispositivos("output") == [
        "Headset 1",
        "Headset 2",
        "Headset 3",
        "Headset 4",
    ]
    assert audio._chosen_api == {
        "input": "directsound",
        "output": "directsound",
    }


def test_saved_choice_persists_by_name_outside_repository(tmp_path, monkeypatch):
    path = tmp_path / "local" / "audio_devices.json"
    monkeypatch.setattr(audio, "_config_path", lambda: path)

    audio.salvar_escolha("input", "Meu Microfone")
    audio.salvar_escolha("output", "Meu Headset")

    assert audio.carregar_escolha("input") == "Meu Microfone"
    assert audio.carregar_escolha("output") == "Meu Headset"
    assert path.exists()
    assert "index" not in path.read_text(encoding="utf-8").lower()


def test_empty_choice_means_system_default():
    audio.salvar_escolha("input", "")
    assert audio.carregar_escolha("input") == ""


def test_missing_name_resolves_to_default_and_logs_warning(monkeypatch, caplog):
    devices, apis = _devices()
    monkeypatch.setattr(
        audio,
        "_obter_sounddevice",
        lambda: FakeSoundDevice(devices, apis),
    )
    with caplog.at_level(logging.WARNING, logger="auren.voice.audio"):
        assert audio.resolver_dispositivo("Fone que não existe", "output") is None
    assert "usando padrão do sistema" in caplog.text


def test_unopenable_exact_name_resolves_to_default(monkeypatch, caplog):
    devices, apis = _devices()
    fake = FakeSoundDevice(devices, apis)
    monkeypatch.setattr(audio, "_obter_sounddevice", lambda: fake)
    original = audio._usable
    monkeypatch.setattr(
        audio,
        "_usable",
        lambda idx, kind, sd: (
            False
            if kind == "input" and devices[idx]["name"] == "Mic 1"
            else original(idx, kind, sd)
        ),
    )
    with caplog.at_level(logging.WARNING, logger="auren.voice.audio"):
        assert audio.resolver_dispositivo("Mic 1", "input") is None


def test_optional_output_probe_rejects_silent_sink(monkeypatch):
    devices, apis = _devices()
    fake = FakeSoundDevice(devices, apis, slow_output=False)
    monkeypatch.setattr(audio, "_obter_sounddevice", lambda: fake)
    assert audio._transport_works(0, "output", "directsound", fake) is False


def test_optional_output_probe_accepts_measured_transport(monkeypatch):
    devices, apis = _devices()
    fake = FakeSoundDevice(devices, apis, slow_output=True)
    monkeypatch.setattr(audio, "_obter_sounddevice", lambda: fake)
    assert audio._transport_works(0, "output", "directsound", fake) is True


def test_device_resolution_uses_live_enumeration(monkeypatch):
    devices, apis = _devices()
    monkeypatch.setattr(
        audio,
        "_obter_sounddevice",
        lambda: FakeSoundDevice(devices, apis),
    )
    assert audio.resolver_dispositivo("Headset 2", "output") == 13
    for device in devices:
        if device["name"] == "Headset 2":
            device["name"] = "Outro nome"
    audio._cache = None
    assert audio.resolver_dispositivo("Headset 2", "output") is None


def test_long_name_can_resolve_against_truncated_backend_name(monkeypatch):
    devices, apis = _devices()
    devices[0]["name"] = "Microfone Extremamente Longo do Auren"
    monkeypatch.setattr(
        audio,
        "_obter_sounddevice",
        lambda: FakeSoundDevice(devices, apis),
    )
    assert (
        audio.resolver_dispositivo(
            "Microfone Extremamente Longo do Auren",
            "input",
        )
        == 0
    )


def test_invalid_direction_is_rejected():
    with pytest.raises(ValueError):
        audio.listar_dispositivos("sideways")


def test_input_captures_resolve_saved_name_on_every_use(monkeypatch):
    import numpy as np

    from voice import input as input_module

    choices = iter(["Microfone A", "Microfone B"])
    resolved = iter([4, 7])
    seen = []

    class Keyboard:
        def __init__(self):
            self.press_calls = 0

        def is_pressed(self, key):
            if key == "esc":
                return False
            self.press_calls += 1
            return self.press_calls in {1, 3}

    class StreamContext:
        def __init__(self, **kwargs):
            seen.append(kwargs["device"])
            self.callback = kwargs["callback"]

        def __enter__(self):
            self.callback(np.array([[0.2], [0.3]] * 1600, dtype=np.float32), 3200, None, None)
            return self

        def __exit__(self, *args):
            return False

    class SoundDevice:
        def query_devices(self, device=None, kind=None):
            if device is not None:
                return {
                    "name": f"Mic {device}",
                    "default_samplerate": 16000,
                }
            return {"name": "Padrão", "default_samplerate": 16000}

        def InputStream(self, **kwargs):
            return StreamContext(**kwargs)

    monkeypatch.setattr(input_module, "carregar_escolha", lambda _kind: next(choices))
    monkeypatch.setattr(input_module, "resolver_dispositivo", lambda _name, _kind: next(resolved))

    recorder = input_module.PushToTalkRecorder(
        hotkey="f8",
        config=input_module.AudioCaptureConfig(min_seconds=0.1),
        sounddevice_module=SoundDevice(),
        keyboard_module=Keyboard(),
    )

    assert recorder.capturar() is not None
    assert recorder.capturar() is not None
    assert seen == [4, 7]


def test_tts_resolves_saved_output_name_when_stream_starts(monkeypatch):
    from voice import tts as tts_module

    resolved = []
    monkeypatch.setattr(tts_module, "carregar_escolha", lambda _kind: "Meu Headset")
    monkeypatch.setattr(
        tts_module,
        "resolver_dispositivo",
        lambda name, kind: resolved.append((name, kind)) or 9,
    )

    class Stream:
        def __init__(self, **kwargs):
            self.device = kwargs["device"]
            self.started = False
            self.writes = 0
            self.stopped = False
            self.closed = False

        def start(self):
            self.started = True

        def write(self, audio):
            self.writes += 1
            assert len(audio) > 0

        def stop(self):
            self.stopped = True

        def close(self):
            self.closed = True

    class SoundDevice:
        def __init__(self):
            self.stream = None

        def OutputStream(self, **kwargs):
            self.stream = Stream(**kwargs)
            return self.stream

    class Model:
        async def create_stream(self, text, voice, speed, lang):
            assert text == "Olá Auren."
            yield [0.0, 0.1], 24000

    sd = SoundDevice()
    tts = tts_module.LocalKokoroTTS(
        model=Model(),
        sounddevice_module=sd,
    )
    tts.falar("Olá Auren.")

    assert resolved == [("Meu Headset", "output")]
    assert sd.stream.device == 9
    assert sd.stream.started is True
    assert sd.stream.writes == 1
    assert sd.stream.stopped is True
    assert sd.stream.closed is True
