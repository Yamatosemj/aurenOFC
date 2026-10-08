from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

from agent.ari_native.audio_manager import input_session

from voice.segmentation import VoiceActivitySegmenter, VoiceSegmentConfig


@dataclass(frozen=True)
class AudioCaptureConfig:
    channels: int = 1
    dtype: str = "float32"
    min_seconds: float = 0.10
    max_seconds: float = 30.0
    poll_interval: float = 0.02
    sample_rate: int | None = 16_000
    silence_rms: float = 0.0008
    silence_peak: float = 0.005
    pre_roll_seconds: float = 0.18
    post_roll_seconds: float = 0.12
    key_debounce_seconds: float = 0.06


@dataclass(frozen=True)
class CapturedAudio:
    samples: Any
    sample_rate: int
    duration: float
    rms: float
    peak: float
    device_name: str
    speech_detected: bool = False
    vad_backend: str = "unknown"


class PushToTalkRecorder:
    """Captura PTT com pre-roll, pos-roll e segmentacao local da fala.

    O microfone fica aberto somente no processo local enquanto o recorder esta
    esperando F8. Fora da fala, apenas uma janela curta em RAM e mantida para
    evitar cortar a primeira silaba quando o usuario aperta a tecla.
    """

    def __init__(
        self,
        *,
        hotkey: str = "right ctrl",
        config: AudioCaptureConfig | None = None,
        sounddevice_module: Any | None = None,
        keyboard_module: Any | None = None,
        segmenter: VoiceActivitySegmenter | None = None,
    ) -> None:
        self.hotkey = hotkey
        self.config = config or AudioCaptureConfig()
        self._sd = sounddevice_module
        self._keyboard = keyboard_module
        self._lock = Lock()
        self._frames: list[Any] = []
        self._pre_roll: deque[Any] = deque()
        self._pre_roll_samples = 0
        self._pre_roll_limit_samples = 0
        self._recording = False
        self._output_active = False
        self._input_overflow_count = 0
        self._device_index = self._resolve_device_from_env()
        self._last_device_name = ""
        self._last_sample_rate = 16_000
        self.segmenter = segmenter or VoiceActivitySegmenter(
            config=VoiceSegmentConfig(
                min_speech_seconds=max(0.06, min(self.config.min_seconds, 0.12)),
                silence_rms=self.config.silence_rms,
                silence_peak=self.config.silence_peak,
            )
        )

    @staticmethod
    def _resolve_device_from_env() -> int | str | None:
        value = os.getenv("AUREN_MIC_DEVICE", "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value

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
    def _normalizar_nome(valor: Any) -> str:
        return " ".join(str(valor or "").strip().lower().split())

    def _resolver_dispositivo(self) -> int | str | None:
        """Resolve nomes novamente a cada abertura para tolerar indices mutaveis."""

        requested = self._device_index
        if requested is None or isinstance(requested, int):
            return requested

        try:
            devices = list(self._sd.query_devices())
        except Exception:
            return None

        wanted = self._normalizar_nome(requested)
        exact: list[int] = []
        partial: list[int] = []
        for index, info in enumerate(devices):
            if not isinstance(info, dict):
                continue
            if int(info.get("max_input_channels", 0) or 0) <= 0:
                continue
            name = self._normalizar_nome(info.get("name"))
            if not name:
                continue
            if name == wanted:
                exact.append(index)
            elif wanted in name:
                partial.append(index)

        if exact:
            return exact[0]
        if len(partial) == 1:
            return partial[0]

        print(
            f"Auren voz: microfone configurado '{requested}' nao foi encontrado; "
            "usando o dispositivo de entrada padrao."
        )
        return None

    def _input_device_info(self, device: int | str | None) -> tuple[str, int]:
        try:
            info = (
                self._sd.query_devices(device, "input")
                if device is not None
                else self._sd.query_devices(kind="input")
            )
            name = (
                str(info.get("name", "desconhecido"))
                if isinstance(info, dict)
                else str(info)
            )
            default_sr = (
                float(info.get("default_samplerate", 16_000))
                if isinstance(info, dict)
                else 16_000.0
            )
            configured = self.config.sample_rate
            sample_rate = int(configured or round(default_sr) or 16_000)
            return name, sample_rate
        except Exception as exc:
            raise RuntimeError(f"Nao foi possivel consultar o microfone: {exc}") from exc

    def _stream_kwargs(self, *, device: int | str | None, sample_rate: int) -> dict[str, Any]:
        blocksize = max(1, int(round(sample_rate * 0.04)))
        return {
            "samplerate": int(sample_rate),
            "channels": self.config.channels,
            "dtype": self.config.dtype,
            "blocksize": blocksize,
            "latency": "high",
            "callback": self._callback,
            "device": device,
        }

    def _abrir_stream(
        self,
        *,
        device: int | str | None,
        device_name: str,
        preferred_rate: int,
        native_rate: int,
    ) -> tuple[Any, int]:
        rates: list[int] = []
        for rate in (preferred_rate, native_rate):
            normalized = int(rate or 16_000)
            if normalized not in rates:
                rates.append(normalized)

        errors: list[str] = []
        for rate in rates:
            stream = None
            try:
                stream = self._sd.InputStream(**self._stream_kwargs(device=device, sample_rate=rate))
                stream.start()
                return stream, rate
            except Exception as exc:
                errors.append(f"{rate} Hz: {exc}")
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

        raise RuntimeError(
            f"Nao foi possivel abrir o microfone '{device_name}'. "
            + " | ".join(errors)
        )

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        del frames, time_info
        if status:
            # Nunca imprimimos dentro do callback: I/O aqui pode aumentar o
            # proprio risco de overflow. O contador e reportado apos a captura.
            status_text = str(status).lower()
            if "input overflow" in status_text:
                with self._lock:
                    self._input_overflow_count += 1

        copy = getattr(indata, "copy", None)
        chunk = copy() if callable(copy) else indata
        try:
            chunk_samples = int(getattr(chunk, "shape", [len(chunk)])[0])
        except Exception:
            return

        with self._lock:
            if self._recording:
                self._frames.append(chunk)
                return

            if self._output_active:
                # Nao contaminamos o pre-roll com a voz do proprio Auren.
                return

            self._pre_roll.append(chunk)
            self._pre_roll_samples += chunk_samples
            while (
                self._pre_roll
                and self._pre_roll_samples > self._pre_roll_limit_samples
            ):
                old = self._pre_roll.popleft()
                try:
                    self._pre_roll_samples -= int(getattr(old, "shape", [len(old)])[0])
                except Exception:
                    self._pre_roll_samples = 0

    def _preparar_buffer(self, sample_rate: int) -> None:
        with self._lock:
            self._pre_roll.clear()
            self._pre_roll_samples = 0
            self._pre_roll_limit_samples = max(
                1,
                int(round(sample_rate * max(0.0, self.config.pre_roll_seconds))),
            )

    def _registrar_inicio(self) -> None:
        with self._lock:
            self._frames = list(self._pre_roll)
            self._pre_roll.clear()
            self._pre_roll_samples = 0
            self._recording = True

    def _registrar_fim(self) -> list[Any]:
        with self._lock:
            self._recording = False
            frames = list(self._frames)
            self._frames = []
        return frames

    def definir_saida_ativa(self, ativa: bool) -> None:
        """Impede o pre-roll de armazenar a voz do TTS durante a resposta."""

        with self._lock:
            self._output_active = bool(ativa)
            if ativa:
                self._pre_roll.clear()
                self._pre_roll_samples = 0

    def limpar_pre_roll(self) -> None:
        with self._lock:
            self._pre_roll.clear()
            self._pre_roll_samples = 0

    def capturar(self) -> CapturedAudio | None:
        """Aguarda Ctrl direito, preserva contexto de borda e entrega audio segmentado."""
        self._load_dependencies()
        with input_session():
            return self._capturar_com_lock()

    def _capturar_com_lock(self) -> CapturedAudio | None:
        sd = self._sd
        keyboard = self._keyboard

        requested_device = self._resolver_dispositivo()
        try:
            device_name, native_rate = self._input_device_info(requested_device)
        except RuntimeError:
            if requested_device is None:
                raise
            print(
                "Auren voz: microfone selecionado indisponivel; tentando o padrao."
            )
            requested_device = None
            device_name, native_rate = self._input_device_info(None)

        preferred_rate = int(self.config.sample_rate or native_rate)
        stream = None
        actual_rate = preferred_rate

        try:
            try:
                stream, actual_rate = self._abrir_stream(
                    device=requested_device,
                    device_name=device_name,
                    preferred_rate=preferred_rate,
                    native_rate=native_rate,
                )
            except RuntimeError as selected_error:
                if requested_device is None:
                    raise
                print(
                    f"Auren voz: microfone '{device_name}' falhou; usando o padrao."
                    f" ({selected_error})"
                )
                requested_device = None
                device_name, native_rate = self._input_device_info(None)
                stream, actual_rate = self._abrir_stream(
                    device=None,
                    device_name=device_name,
                    preferred_rate=int(self.config.sample_rate or native_rate),
                    native_rate=native_rate,
                )

            self._last_device_name = device_name
            self._last_sample_rate = actual_rate
            self._preparar_buffer(actual_rate)
            with self._lock:
                self._input_overflow_count = 0
            print(f"Microfone: {device_name} | captura={actual_rate} Hz")
            print(f"Segure {self.hotkey.upper()} para falar... (ESC encerra)")

            press_started: float | None = None
            esc_requested = False
            max_duration_reached = False

            while True:
                if keyboard.is_pressed("esc"):
                    esc_requested = True
                    break

                if keyboard.is_pressed(self.hotkey):
                    now = time.perf_counter()
                    if press_started is None:
                        press_started = now
                    elif now - press_started >= self.config.key_debounce_seconds:
                        break
                else:
                    press_started = None

                time.sleep(self.config.poll_interval)

            if esc_requested:
                return None

            self._registrar_inicio()
            started = time.perf_counter()

            while True:
                if keyboard.is_pressed("esc"):
                    esc_requested = True
                    break

                if not keyboard.is_pressed(self.hotkey):
                    break

                if time.perf_counter() - started >= self.config.max_seconds:
                    max_duration_reached = True
                    break

                time.sleep(self.config.poll_interval)

            if not esc_requested:
                if max_duration_reached:
                    print("Auren voz: limite maximo de fala atingido.")
                    while keyboard.is_pressed(self.hotkey) and not keyboard.is_pressed("esc"):
                        time.sleep(self.config.poll_interval)

                if not keyboard.is_pressed("esc"):
                    deadline = time.perf_counter() + max(0.0, self.config.post_roll_seconds)
                    while time.perf_counter() < deadline:
                        if keyboard.is_pressed("esc"):
                            esc_requested = True
                            break
                        time.sleep(self.config.poll_interval)

        except Exception:
            with self._lock:
                self._recording = False
                self._frames = []
                self._pre_roll.clear()
                self._pre_roll_samples = 0
            raise
        finally:
            try:
                if stream is not None:
                    stream.stop()
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

        frames = self._registrar_fim()
        with self._lock:
            overflow_count = self._input_overflow_count
            self._input_overflow_count = 0
        if overflow_count:
            print(f"Auren voz: {overflow_count} avisos de input overflow durante a captura.")
        if esc_requested or not frames:
            return None

        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Dependencia numpy ausente. Rode INSTALAR_VOZ.bat.") from exc

        audio = np.concatenate(frames, axis=0)
        if audio.ndim == 2:
            audio = np.mean(audio, axis=1)
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        if audio.size == 0:
            return None

        duration = float(audio.shape[0]) / float(actual_rate)
        if duration < self.config.min_seconds:
            return None

        segment = self.segmenter.segment(audio, actual_rate)
        if segment is None:
            print("Auren voz: audio sem fala utilizavel; nao enviei para o ASR.")
            return None

        samples = np.asarray(segment.samples, dtype=np.float32).reshape(-1)
        duration = float(samples.size) / float(segment.sample_rate)
        if duration < self.config.min_seconds:
            return None

        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
        peak = float(np.max(np.abs(samples)))
        print(
            f"Audio pronto para ASR: {duration:.2f}s | "
            f"RMS={rms:.4f} | pico={peak:.4f} | "
            f"segmentacao={segment.vad_backend}"
        )

        return CapturedAudio(
            samples=samples,
            sample_rate=segment.sample_rate,
            duration=duration,
            rms=rms,
            peak=peak,
            device_name=device_name,
            speech_detected=segment.speech_detected,
            vad_backend=segment.vad_backend,
        )

    def hotkey_pressionada(self) -> bool:
        """Retorna se a tecla de push-to-talk esta pressionada neste momento."""
        self._load_dependencies()
        return bool(self._keyboard.is_pressed(self.hotkey))

    def pediu_saida(self) -> bool:
        self._load_dependencies()
        return bool(self._keyboard.is_pressed("esc"))


AudioCapture = PushToTalkRecorder
