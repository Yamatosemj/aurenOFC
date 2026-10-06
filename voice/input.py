from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Event, Lock

from agent.ari_native.audio_manager import input_session
from typing import Any


@dataclass(frozen=True)
class AudioCaptureConfig:
    channels: int = 1
    dtype: str = "float32"
    min_seconds: float = 0.18
    max_seconds: float = 30.0
    poll_interval: float = 0.01
    sample_rate: int | None = None
    silence_rms: float = 0.0008


@dataclass(frozen=True)
class CapturedAudio:
    samples: Any
    sample_rate: int
    duration: float
    rms: float
    peak: float
    device_name: str


class PushToTalkRecorder:
    """Captura audio enquanto uma tecla global permanece pressionada."""

    def __init__(
        self,
        *,
        hotkey: str = "f8",
        config: AudioCaptureConfig | None = None,
        sounddevice_module: Any | None = None,
        keyboard_module: Any | None = None,
    ) -> None:
        self.hotkey = hotkey
        self.config = config or AudioCaptureConfig()
        self._sd = sounddevice_module
        self._keyboard = keyboard_module
        self._lock = Lock()
        self._frames: list[Any] = []
        self._recording = False
        self._device_index = self._resolve_device_from_env()
        self._last_device_name = ""
        self._last_sample_rate = 16_000

    def _load_dependencies(self) -> None:
        if self._sd is None:
            try:
                import sounddevice as sd
            except ImportError as exc:
                raise RuntimeError(
                    "Dependencia de captura ausente. Rode INSTALAR_VOZ.bat."
                ) from exc
            self._sd = sd

        if self._keyboard is None:
            try:
                import keyboard
            except ImportError as exc:
                raise RuntimeError(
                    "Dependencia de tecla global ausente. Rode INSTALAR_VOZ.bat."
                ) from exc
            self._keyboard = keyboard

    @staticmethod
    def _resolve_device_from_env() -> int | str | None:
        value = os.getenv("AUREN_MIC_DEVICE", "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value

    def _input_device_info(self) -> tuple[str, int]:
        try:
            info = (
                self._sd.query_devices(self._device_index, "input")
                if self._device_index is not None
                else self._sd.query_devices(kind="input")
            )
            name = str(info.get("name", "desconhecido")) if isinstance(info, dict) else str(info)
            default_sr = float(info.get("default_samplerate", 16_000)) if isinstance(info, dict) else 16_000.0
            configured = self.config.sample_rate
            sample_rate = int(configured or round(default_sr) or 16_000)
            return name, sample_rate
        except Exception as exc:
            raise RuntimeError(f"Nao foi possivel consultar o microfone: {exc}") from exc

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        del frames, time_info
        if status:
            pass
        with self._lock:
            if self._recording:
                copy = getattr(indata, "copy", None)
                self._frames.append(copy() if callable(copy) else indata)

    def _registrar_inicio(self) -> None:
        with self._lock:
            self._frames = []
            self._recording = True

    def _registrar_fim(self) -> list[Any]:
        with self._lock:
            self._recording = False
            frames = list(self._frames)
            self._frames = []
        return frames

    def capturar(self) -> CapturedAudio | None:
        """Captura uma fala e preserva a taxa nativa do microfone."""
        self._load_dependencies()
        sd = self._sd
        keyboard = self._keyboard

        device_name, sample_rate = self._input_device_info()
        self._last_device_name = device_name
        self._last_sample_rate = sample_rate
        print(f"Microfone: {device_name} | captura={sample_rate} Hz")

        print(f"Segure {self.hotkey.upper()} para falar... (ESC encerra)")
        while not keyboard.is_pressed(self.hotkey):
            if keyboard.is_pressed("esc"):
                return None
            time.sleep(self.config.poll_interval)

        self._registrar_inicio()
        started = time.perf_counter()
        try:
            with input_session():
                with sd.InputStream(
                    samplerate=sample_rate,
                    channels=self.config.channels,
                    dtype=self.config.dtype,
                    callback=self._callback,
                    device=self._device_index,
                ):
                    while keyboard.is_pressed(self.hotkey):
                        if keyboard.is_pressed("esc"):
                            break
                        if time.perf_counter() - started >= self.config.max_seconds:
                            break
                        time.sleep(self.config.poll_interval)
        except Exception as exc:
            with self._lock:
                self._recording = False
                self._frames = []
            raise RuntimeError(f"Nao foi possivel capturar o microfone: {exc}") from exc

        frames = self._registrar_fim()
        if not frames:
            return None

        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Dependencia numpy ausente. Rode INSTALAR_VOZ.bat.") from exc

        audio = np.concatenate(frames, axis=0)
        if audio.ndim == 2 and audio.shape[1] == 1:
            audio = audio[:, 0]
        if audio.size == 0:
            return None

        audio = audio.astype(np.float32, copy=False)
        duration = float(audio.shape[0]) / float(sample_rate)
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
        peak = float(np.max(np.abs(audio)))
        print(f"Audio capturado: {duration:.2f}s | RMS={rms:.4f} | pico={peak:.4f}")

        if duration < self.config.min_seconds:
            return None
        if rms < self.config.silence_rms and peak < 0.005:
            print("Auren voz: audio quase silencioso; nao enviei para o ASR.")
            return None

        return CapturedAudio(
            samples=audio,
            sample_rate=sample_rate,
            duration=duration,
            rms=rms,
            peak=peak,
            device_name=device_name,
        )

    def hotkey_pressionada(self) -> bool:
        """Retorna se a tecla de push-to-talk esta pressionada neste momento."""
        self._load_dependencies()
        return bool(self._keyboard.is_pressed(self.hotkey))

    def pediu_saida(self) -> bool:
        self._load_dependencies()
        return bool(self._keyboard.is_pressed("esc"))


AudioCapture = PushToTalkRecorder
