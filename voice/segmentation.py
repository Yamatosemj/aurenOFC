from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceSegmentConfig:
    """Parametros de segmentacao local da fala."""

    frame_duration_ms: int = 20
    vad_mode: int = 1
    min_speech_seconds: float = 0.08
    start_padding_ms: int = 80
    end_padding_ms: int = 120
    silence_rms: float = 0.0008
    silence_peak: float = 0.005
    vad_sample_rate: int = 16_000


@dataclass(frozen=True)
class VoiceSegment:
    samples: Any
    sample_rate: int
    duration: float
    speech_detected: bool
    vad_backend: str


_SUPPORTED_VAD_RATES = {8_000, 16_000, 32_000, 48_000}


class VoiceActivitySegmenter:
    """Segmenta uma captura PTT sem depender do modelo STT.

    O WebRTC VAD e usado quando instalado. Sem ele, a camada cai para um
    detector de energia simples, mantendo o Auren utilizavel mesmo durante uma
    instalacao incompleta da camada de voz.
    """

    def __init__(
        self,
        *,
        config: VoiceSegmentConfig | None = None,
        vad: Any | None = None,
    ) -> None:
        self.config = config or VoiceSegmentConfig()
        self._vad = vad
        self._vad_load_attempted = vad is not None

    @property
    def backend(self) -> str:
        self._load_vad()
        return "webrtcvad" if self._vad not in (None, False) else "energy"

    def _load_vad(self) -> None:
        if self._vad_load_attempted:
            return
        self._vad_load_attempted = True
        try:
            import webrtcvad
        except ImportError:
            self._vad = False
            return
        except Exception:
            self._vad = False
            return

        try:
            self._vad = webrtcvad.Vad(int(self.config.vad_mode))
        except Exception:
            self._vad = False

    @staticmethod
    def _resample_for_vad(audio: Any, sample_rate: int, target_rate: int) -> tuple[Any, int]:
        import numpy as np

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        sr = int(sample_rate)
        target = int(target_rate)
        if waveform.size == 0 or sr == target:
            return waveform, sr

        target_length = max(1, int(round(waveform.size * target / sr)))
        old_positions = np.linspace(0.0, 1.0, waveform.size, dtype=np.float64)
        new_positions = np.linspace(0.0, 1.0, target_length, dtype=np.float64)
        resampled = np.interp(new_positions, old_positions, waveform)
        return resampled.astype(np.float32, copy=False), target

    @staticmethod
    def _preparar_nivel_para_vad(audio: Any) -> Any:
        """Eleva sinais muito baixos apenas para a decisão do VAD."""
        import numpy as np

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        if waveform.size == 0:
            return waveform
        rms = float(np.sqrt(np.mean(np.square(waveform.astype(np.float64)))))
        peak = float(np.max(np.abs(waveform)))
        if rms <= 0.0 or peak <= 0.0:
            return waveform

        target_rms = 0.02
        max_gain = 6.0
        gain = min(max_gain, max(1.0, target_rms / rms))
        if peak * gain > 0.95:
            gain = min(gain, 0.95 / peak)
        return (waveform * np.float32(gain)).astype(np.float32, copy=False)

    @staticmethod
    def _pcm16_bytes(audio: Any) -> bytes:
        import numpy as np

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        clipped = np.clip(waveform, -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16).tobytes()

    def _webrtc_flags(self, audio: Any, sample_rate: int) -> tuple[list[bool], int]:
        self._load_vad()
        if self._vad in (None, False):
            return [], sample_rate

        vad_audio, vad_rate = self._resample_for_vad(
            audio,
            sample_rate,
            self.config.vad_sample_rate,
        )
        vad_audio = self._preparar_nivel_para_vad(vad_audio)
        if vad_rate not in _SUPPORTED_VAD_RATES:
            return [], vad_rate

        frame_samples = int(round(vad_rate * self.config.frame_duration_ms / 1000.0))
        if frame_samples <= 0:
            return [], vad_rate

        total_frames = len(vad_audio) // frame_samples
        flags: list[bool] = []
        for index in range(total_frames):
            start = index * frame_samples
            end = start + frame_samples
            frame = vad_audio[start:end]
            try:
                flags.append(bool(self._vad.is_speech(self._pcm16_bytes(frame), vad_rate)))
            except Exception:
                return [], vad_rate
        return flags, vad_rate

    def _energy_flags(self, audio: Any, sample_rate: int) -> tuple[list[bool], int]:
        import numpy as np

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        frame_samples = max(1, int(round(sample_rate * self.config.frame_duration_ms / 1000.0)))
        total_frames = len(waveform) // frame_samples
        if total_frames == 0:
            return [], sample_rate

        rms_values: list[float] = []
        peaks: list[float] = []
        for index in range(total_frames):
            frame = waveform[index * frame_samples : (index + 1) * frame_samples]
            rms_values.append(float(np.sqrt(np.mean(np.square(frame.astype(np.float64))))))
            peaks.append(float(np.max(np.abs(frame))) if frame.size else 0.0)

        values = np.asarray(rms_values, dtype=np.float64)
        noise_floor = float(np.percentile(values, 20))
        threshold = max(
            float(self.config.silence_rms),
            noise_floor * 2.0,
        )
        flags = [
            rms >= threshold and peak >= self.config.silence_peak * 0.35
            for rms, peak in zip(rms_values, peaks)
        ]
        return flags, sample_rate

    def _bounds_from_flags(
        self,
        flags: list[bool],
        *,
        frame_rate: int,
        original_sample_rate: int,
        original_duration: float,
    ) -> tuple[int, int] | None:
        if not flags:
            return None

        active_indices = [index for index, active in enumerate(flags) if active]
        if not active_indices:
            return None

        speech_duration = len(active_indices) * self.config.frame_duration_ms / 1000.0
        if speech_duration < self.config.min_speech_seconds:
            return None

        frame_seconds = self.config.frame_duration_ms / 1000.0
        start_seconds = max(
            0.0,
            active_indices[0] * frame_seconds - self.config.start_padding_ms / 1000.0,
        )
        end_seconds = min(
            original_duration,
            (active_indices[-1] + 1) * frame_seconds + self.config.end_padding_ms / 1000.0,
        )

        start = max(0, int(math.floor(start_seconds * original_sample_rate)))
        end = min(
            int(round(original_duration * original_sample_rate)),
            int(math.ceil(end_seconds * original_sample_rate)),
        )
        if end <= start:
            return None
        return start, end

    def segment(self, audio: Any, sample_rate: int) -> VoiceSegment | None:
        import numpy as np

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        sr = int(sample_rate)
        if waveform.size == 0 or sr <= 0:
            return None

        waveform = np.nan_to_num(waveform, nan=0.0, posinf=0.0, neginf=0.0)
        duration = float(waveform.size) / float(sr)
        if duration < self.config.min_speech_seconds:
            return None

        rms = float(np.sqrt(np.mean(np.square(waveform.astype(np.float64)))))
        peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
        if rms < self.config.silence_rms and peak < self.config.silence_peak:
            return None

        self._load_vad()
        flags, frame_rate = self._webrtc_flags(waveform, sr)
        backend = "webrtcvad"
        if not flags or not any(flags):
            flags, frame_rate = self._energy_flags(waveform, sr)
            backend = "energy"

        bounds = self._bounds_from_flags(
            flags,
            frame_rate=frame_rate,
            original_sample_rate=sr,
            original_duration=duration,
        )

        if bounds is None:
            # O VAD pode ser conservador em fala muito baixa. O gate de ruido
            # acima ja rejeitou silencio quase puro; neste caso preservamos a
            # captura em vez de correr o risco de apagar uma frase valida.
            return VoiceSegment(
                samples=waveform,
                sample_rate=sr,
                duration=duration,
                speech_detected=False,
                vad_backend=backend,
            )

        start, end = bounds
        trimmed = waveform[start:end]
        trimmed_duration = float(trimmed.size) / float(sr)
        if trimmed_duration < self.config.min_speech_seconds:
            return None

        return VoiceSegment(
            samples=trimmed,
            sample_rate=sr,
            duration=trimmed_duration,
            speech_detected=True,
            vad_backend=backend,
        )
